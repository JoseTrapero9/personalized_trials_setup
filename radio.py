"""Plant radio playback: loads the generated clips and plays them on the participant's headphones.

One persistent output stream; the game asks for one clip at a time and polls when it ends.
If the audio files or the output device are missing, it runs in SILENT mode (correct timing,
no sound) so the paradigm can still be tested; a warning is printed and an LSL marker is sent.
"""

import json
import os
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import RADIO_AUDIO_DIR, RADIO_FX, RADIO_STATIC_DB, RADIO_VOLUME


class ClipBank:
    def __init__(self, lang, samplerate):
        self.lang = lang
        self.sr = samplerate
        self.clips = {}          # id -> float32 mono array (or None in silent mode)
        self.durations = {}      # id -> seconds
        self.voice = None
        self.problems = []
        self.ok = False
        self._load()

    def _load(self):
        folder = os.path.join(RADIO_AUDIO_DIR, self.lang)
        manifest_path = os.path.join(folder, "manifest.json")
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            self.problems.append(f"no radio audio for '{self.lang}' "
                                 f"(run: python generate_radio_audio.py --lang {self.lang})")
            return
        self.voice = manifest.get("voice")
        for cid, entry in manifest.get("clips", {}).items():
            path = os.path.join(folder, cid + ".wav")
            try:
                x, fs = sf.read(path, dtype="float32", always_2d=True)
            except Exception:
                self.problems.append(f"missing {cid}.wav")
                continue
            x = x.mean(axis=1)
            if fs != self.sr:
                n = int(round(len(x) * self.sr / fs))
                x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
            if RADIO_FX:
                x = _radio_fx(x, self.sr)
            self.clips[cid] = x * RADIO_VOLUME
            self.durations[cid] = len(x) / self.sr
        self.ok = bool(self.clips)

    def has(self, cid):
        return cid in self.durations

    def check(self, expected_ids):
        missing = [c for c in expected_ids if c not in self.durations]
        if missing:
            self.problems.append(f"{len(missing)} clips missing (e.g. {missing[0]}); "
                                 f"re-run generate_radio_audio.py --lang {self.lang}")
        return not missing


def _radio_fx(x, sr):
    """Light 'radio' sound: band-pass 250-4500 Hz (stays intelligible on bone conduction)."""
    n = len(x)
    if n < 64:
        return x
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    gain = np.clip((f - 150) / 100, 0, 1) * np.clip((5500 - f) / 1000, 0, 1)
    y = np.fft.irfft(spec * gain, n).astype(np.float32)
    y = np.tanh(1.6 * y) / np.tanh(1.6)              # soft saturation
    peak = np.max(np.abs(y)) or 1.0
    return (y * (np.max(np.abs(x)) / peak)).astype(np.float32)


class RadioPlayer:
    def __init__(self, device=None, samplerate=44100):
        self.device = device
        self.sr = samplerate
        self.stream = None
        self._lock = threading.Lock()
        self._buf = None
        self._pos = 0
        self._cid = None
        self._finished = None
        self._silent_end = None          # silent mode: perf_counter time the clip "ends"
        self._overlays = []              # cue sounds mixed on top of the radio: [samples, position]
        self._cue_cache = {}             # (path, max seconds) -> samples at this stream's rate
        self.static_amp = 10 ** (RADIO_STATIC_DB / 20) if RADIO_STATIC_DB is not None else 0.0
        self._rng = np.random.default_rng()
        self._open()

    def _open(self):
        for sr in (self.sr, None):
            try:
                if sr is None:
                    info = sd.query_devices(self.device, "output")
                    sr = int(info["default_samplerate"])
                self.stream = sd.OutputStream(device=self.device, samplerate=sr, channels=2,
                                              dtype="float32", callback=self._callback, blocksize=512)
                self.stream.start()
                self.sr = sr
                print(f"Radio output: device {self.device}, {sr} Hz")
                return
            except Exception as e:
                last = e
                self.stream = None
        print(f"WARNING: radio output stream failed ({last}). Radio runs SILENT.")

    @property
    def silent(self):
        return self.stream is None

    def _callback(self, outdata, frames, time_info, status):
        out = np.zeros(frames, dtype=np.float32)
        with self._lock:
            if self._buf is not None:
                n = min(frames, len(self._buf) - self._pos)
                out[:n] = self._buf[self._pos:self._pos + n]
                self._pos += n
                if self._pos >= len(self._buf):
                    self._finished = self._cid
                    self._buf, self._cid = None, None
            if self._overlays:
                for item in self._overlays:
                    buf, pos = item
                    n = min(frames, len(buf) - pos)
                    out[:n] += buf[pos:pos + n]
                    item[1] = pos + n
                self._overlays = [it for it in self._overlays if it[1] < len(it[0])]
        if self.static_amp:
            out += self.static_amp * self._rng.standard_normal(frames).astype(np.float32)
        np.clip(out, -1.0, 1.0, out=out)
        outdata[:, 0] = out
        outdata[:, 1] = out

    def play(self, cid, samples, duration):
        with self._lock:
            self._finished = None
            self._cid = cid
            if self.silent or samples is None:
                self._buf = None
                self._silent_end = time.perf_counter() + duration
            else:
                self._buf = samples
                self._pos = 0
                self._silent_end = None

    def play_cue(self, path, max_seconds=1.0):
        """Mix a short cue sound into the running stream, on top of whatever the radio is saying.
        The stream is already open, so the cue starts with the next audio block (about 12 ms) instead of
        waiting for a new stream to open. Cut to max_seconds with a 30 ms fade-out. False if not possible."""
        if self.silent:
            return False
        key = (path, max_seconds)
        if key not in self._cue_cache:
            try:
                x, fs = sf.read(path, dtype="float32", always_2d=True)
            except Exception as e:
                print(f"Cue sound not readable: {path} ({e})")
                self._cue_cache[key] = None
                return False
            x = x.mean(axis=1)[:int(fs * max_seconds)]
            fade = min(len(x), int(0.03 * fs))
            if fade > 0:
                x[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
            if fs != self.sr:
                n = int(round(len(x) * self.sr / fs))
                x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
            self._cue_cache[key] = np.ascontiguousarray(x, dtype=np.float32)
        samples = self._cue_cache[key]
        if samples is None:
            return False
        with self._lock:
            self._overlays.append([samples, 0])
        return True

    def stop(self):
        with self._lock:
            self._buf, self._cid, self._finished, self._silent_end = None, None, None, None

    def busy(self):
        self._check_silent()
        with self._lock:
            return self._cid is not None

    def poll_finished(self):
        """Clip id that just finished (once), else None."""
        self._check_silent()
        with self._lock:
            cid, self._finished = self._finished, None
            return cid

    def _check_silent(self):
        with self._lock:
            if self._silent_end is not None and time.perf_counter() >= self._silent_end:
                self._finished = self._cid
                self._cid, self._silent_end = None, None

    def close(self):
        self.stop()
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
