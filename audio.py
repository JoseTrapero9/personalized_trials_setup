"""Audio output: participant (bone-conduction) / researcher devices, one-shot clips, alarm loop."""

import os
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioController:
    def __init__(self):
        self.participant_device = None
        self.researcher_device = None
        self.alarm_active = False
        self._clips = {}           # (path, max seconds) -> (samples, rate) of the cue sounds

    def setup_devices(self, participant_keyword, researcher_keyword):
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d['max_output_channels'] > 0:
                name = d['name'].lower()
                if participant_keyword.lower() in name and self.participant_device is None:
                    self.participant_device = i
                    print(f"Participant Audio set to Device {i}: {d['name']}")
                elif researcher_keyword.lower() in name and self.researcher_device is None:
                    self.researcher_device = i
                    print(f"Researcher Audio set to Device {i}: {d['name']}")

    def play_participant(self, filepath):
        if os.path.exists(filepath):
            threading.Thread(target=self._play_audio, args=(filepath, self.participant_device), daemon=True).start()

    def play_researcher(self, filepath):
        if os.path.exists(filepath):
            threading.Thread(target=self._play_audio, args=(filepath, self.researcher_device), daemon=True).start()

    def play_both(self, filepath):
        if os.path.exists(filepath):
            if self.participant_device is not None:
                threading.Thread(target=self._play_audio, args=(filepath, self.participant_device), daemon=True).start()
            if self.researcher_device is not None:
                threading.Thread(target=self._play_audio, args=(filepath, self.researcher_device), daemon=True).start()

    def play_participant_clip(self, filepath, max_seconds=1.0):
        """Cue sound for the participant, never longer than max_seconds (30 ms fade-out at the cut).
        The clip is loaded once and kept in memory, so the cue starts without reading the file again."""
        clip = self._load_clip(filepath, max_seconds)
        if clip is not None:
            threading.Thread(target=self._play_data, args=(clip[0], clip[1], self.participant_device),
                             daemon=True).start()

    def _load_clip(self, filepath, max_seconds):
        key = (filepath, max_seconds)
        if key not in self._clips:
            if not os.path.exists(filepath):
                print(f"Cue sound not found: {filepath}")
                return None
            data, fs = sf.read(filepath, dtype='float32', always_2d=True)
            data = data[:int(fs * max_seconds)].copy()
            fade = min(len(data), int(0.03 * fs))
            if fade > 0:
                data[-fade:] *= np.linspace(1.0, 0.0, fade, dtype='float32')[:, None]
            if data.shape[1] == 1:
                data = np.column_stack((data, data))
            self._clips[key] = (data, fs)
        return self._clips[key]

    def _play_data(self, data, fs, device_id):
        try:
            with sd.OutputStream(device=device_id, samplerate=fs, channels=data.shape[1], dtype='float32') as stream:
                stream.write(data)
        except Exception as e:
            print(f"Error playing cue sound: {e}")

    def _play_audio(self, filepath, device_id):
        if not os.path.exists(filepath):
            return
        try:
            data, fs = sf.read(filepath, dtype='float32')
            if data.ndim == 1:
                data = np.column_stack((data, data))
            channels = data.shape[1]

            with sd.OutputStream(device=device_id, samplerate=fs, channels=channels, dtype='float32') as stream:
                stream.write(data)
                time.sleep(0.05)
        except Exception as e:
            print(f"Error playing {filepath}: {e}")

    def start_looping_alarm(self, filepath, volume=0.3):
        if self.alarm_active or not os.path.exists(filepath):
            return
        self.alarm_active = True
        threading.Thread(
            target=self._loop_worker,
            args=(filepath, self.researcher_device, volume),
            daemon=True,
        ).start()

    def stop_looping_alarm(self):
        self.alarm_active = False

    def _loop_worker(self, filepath, device_id, volume=0.3):
        try:
            data, fs = sf.read(filepath, dtype='float32')
            if data.ndim == 1:
                data = np.column_stack((data, data))
            channels = data.shape[1]
            scaled_data = data * volume

            while self.alarm_active:
                with sd.OutputStream(device=device_id, samplerate=fs, channels=channels, dtype='float32') as stream:
                    stream.write(scaled_data)
        except Exception as e:
            print(f'Alarm loop error: {e}')


audio_sys = AudioController()
