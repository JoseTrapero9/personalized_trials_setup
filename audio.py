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
