import torch
import librosa
import numpy as np
import random
import os
from torch.utils.data import DataLoader
from modules.audio import mel_spectrogram


duration_setting = {
    "min": 1.0,
    "max": 30.0,
}
# assume single speaker
class FT_Dataset(torch.utils.data.Dataset):
    def __init__(self,
                 data_path,
                 spect_params,
                 sr=22050,
                 batch_size=1,
                 ):
        self.data_path = data_path
        # recursively find all files in data_path
        self.data = []
        for root, _, files in os.walk(data_path):
            for file in files:
                if (file.endswith(".wav") or
                        file.endswith(".mp3") or
                        file.endswith(".flac") or
                        file.endswith(".ogg") or
                        file.endswith(".m4a") or
                        file.endswith(".opus")):
                    self.data.append(os.path.join(root, file))

        mel_fn_args = {
            "n_fft": spect_params['n_fft'],
            "win_size": spect_params['win_length'],
            "hop_size": spect_params['hop_length'],
            "num_mels": spect_params['n_mels'],
            "sampling_rate": sr,
            "fmin": spect_params['fmin'],
            "fmax": None if spect_params['fmax'] == "None" else spect_params['fmax'],
            "center": False
        }
        self.to_mel = lambda x: mel_spectrogram(x, **mel_fn_args)
        self.sr = sr

        assert len(self.data) != 0
        # if dataset length is less than batch size, repeat the dataset
        while len(self.data) < batch_size:
            self.data += self.data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        idx = idx % len(self.data)
        wav_path = self.data[idx]
        try:
            speech, orig_sr = librosa.load(wav_path, sr=self.sr)
        except Exception as e:
            print(f"Failed to load wav file with error {e}")
            return self.__getitem__(random.randint(0, len(self)))
        if len(speech) < self.sr * duration_setting["min"] or len(speech) > self.sr * duration_setting["max"]:
            print(f"Audio {wav_path} is too short or too long, skipping")
            return self.__getitem__(random.randint(0, len(self)))
        return_dict = {
            'audio': speech,
            'sr': orig_sr
        }
        wave, orig_sr = return_dict['audio'], return_dict['sr']
        if orig_sr != self.sr:
            wave = librosa.resample(wave, orig_sr, self.sr)
        wave = torch.from_numpy(wave).float()
        mel = self.to_mel(wave.unsqueeze(0)).squeeze(0)

        return wave, mel

def build_ft_dataloader(data_path, spect_params, sr, batch_size=1, num_workers=0):
    dataset = FT_Dataset(data_path, spect_params, sr, batch_size)
    dataloader = torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        collate_fn=collate,
    )
    return dataloader

def collate(batch):
    batch_size = len(batch)

    # sort by mel length
    lengths = [b[1].shape[1] for b in batch]
    batch_indexes = np.argsort(lengths)[::-1]
    batch = [batch[bid] for bid in batch_indexes]

    nmels = batch[0][1].size(0)
    max_mel_length = max([b[1].shape[1] for b in batch])
    max_wave_length = max([b[0].size(0) for b in batch])

    mels = torch.zeros((batch_size, nmels, max_mel_length)).float() - 10
    waves = torch.zeros((batch_size, max_wave_length)).float()

    mel_lengths = torch.zeros(batch_size).long()
    wave_lengths = torch.zeros(batch_size).long()

    for bid, (wave, mel) in enumerate(batch):
        mel_size = mel.size(1)
        mels[bid, :, :mel_size] = mel
        waves[bid, : wave.size(0)] = wave
        mel_lengths[bid] = mel_size
        wave_lengths[bid] = wave.size(0)

    return waves, mels, wave_lengths, mel_lengths

if __name__ == "__main__":
    data_path = "./example/reference"
    sr = 22050
    spect_params = {
        "n_fft": 1024,
        "win_length": 1024,
        "hop_length": 256,
        "n_mels": 80,
        "fmin": 0,
        "fmax": 8000,
    }
    dataloader = build_ft_dataloader(data_path, spect_params, sr, batch_size=2, num_workers=0)
    for idx, batch in enumerate(dataloader):
        wave, mel, wave_lengths, mel_lengths = batch
        print(wave.shape, mel.shape)
        if idx == 10:
            break