"""Offline voice trigger ("deliver") using Vosk, with a Qt signal."""

import json
import os
import queue
import threading
import time

import sounddevice as sd

from PyQt5.QtCore import QObject, pyqtSignal

from config import (
    DELIVER_WORDS,
    VOICE_COOLDOWN_SECONDS,
    VOICE_INPUT_KEYWORD,
    VOSK_MODEL_DIR,
    VOSK_SAMPLE_RATE
)


# Third-party: offline voice recognition (graceful fallback to the 'D' key)
try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)  # silence Kaldi console spam
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    print("Warning: 'vosk' not installed. Use the 'D' key to simulate saying 'deliver'.")


class VoiceDeliverListener(QObject):
    deliver_detected = pyqtSignal()

    def __init__(self, input_keyword=VOICE_INPUT_KEYWORD):
        super().__init__()
        self.input_keyword = input_keyword  # part of the microphone name; None = Windows default mic
        self.status = ""                    # human-readable state (shown by live_evaluator / voice_check)
        self.device_name = ""
        self.sample_rate = VOSK_SAMPLE_RATE
        self.on_text = None                 # optional callback(text, is_final) for everything heard
        self.listening_enabled = False
        self._running = True
        self._needs_reset = False      # worker thread resets the recognizer (keeps Vosk single-threaded)
        self._last_emit = 0.0
        self.q = queue.Queue()
        self.stream = None
        self.thread = None
        self.model = None
        self.rec = None
        self.vosk_ready = False

        if not VOSK_AVAILABLE:
            self.status = "vosk not installed (pip install vosk)"
            return

        if not os.path.exists(VOSK_MODEL_DIR):
            self.status = f"Vosk model not found at {VOSK_MODEL_DIR}"
            print(f"Vosk model folder not found at '{VOSK_MODEL_DIR}'. "
                  f"Voice recognition disabled (use 'D' key fallback).")
            return

        try:
            print("Loading offline Vosk speech model...")
            self.model = Model(VOSK_MODEL_DIR)
            # Grammar restriction: lock recognition to the trigger words only
            self._grammar = json.dumps(list(DELIVER_WORDS) + ["[unk]"])
            self.rec = KaldiRecognizer(self.model, VOSK_SAMPLE_RATE, self._grammar)
            self.vosk_ready = True
            self.status = "model loaded, microphone not opened yet"
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            print("Vosk speech recognition active and ready.")
        except Exception as e:
            print(f"Failed to initialize Vosk model: {e}")
            self.status = f"Vosk model failed to load: {e}"
            self.vosk_ready = False

    # -- helpers ------------------------------------------------------------
    def _find_input_device(self):
        if not self.input_keyword:
            return None
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and self.input_keyword.lower() in d["name"].lower():
                print(f"Voice input set to Device {i}: {d['name']}")
                return i
        print(f"Input device '{self.input_keyword}' not found, using system default.")
        return None

    def _open_stream(self):
        """Opens the microphone at 16 kHz, or at a rate the device accepts (Bluetooth headsets often
        refuse 16 kHz); Vosk is then told the real rate and downsamples itself."""
        device = self._find_input_device()
        try:
            info = sd.query_devices(device, "input")
        except Exception as e:
            self.status = f"no microphone found ({e})"
            print(f"Failed to start microphone stream for Vosk: {e}")
            return
        rates = [VOSK_SAMPLE_RATE, int(info["default_samplerate"]), 48000, 44100, 32000]
        errors = []
        for rate in dict.fromkeys(r for r in rates if r >= VOSK_SAMPLE_RATE):
            try:
                stream = sd.InputStream(device=device, samplerate=rate, channels=1, dtype="int16",
                                        callback=self._audio_callback)
                if rate != self.sample_rate:
                    self.rec = KaldiRecognizer(self.model, rate, self._grammar)
                    self.sample_rate = rate
                stream.start()
                self.stream = stream
                self.device_name = info["name"]
                self.status = f"listening on '{info['name']}' at {rate} Hz"
                print(f"Vosk {self.status}")
                return
            except Exception as e:
                errors.append(f"{rate} Hz: {e}")
        self.status = f"microphone '{info['name']}' could not be opened ({errors[0] if errors else ''})"
        print(f"Failed to start microphone stream for Vosk: {'; '.join(errors)}")

    def _emit_deliver(self):
        now = time.monotonic()
        if now - self._last_emit < VOICE_COOLDOWN_SECONDS:
            return
        self._last_emit = now
        self.deliver_detected.emit()

    # -- public API ---------------------------------------------------------
    def set_enabled(self, enabled: bool):
        self.listening_enabled = enabled
        if not self.vosk_ready:
            return

        if enabled:
            # Drop stale audio from earlier phases and start from a clean recognizer
            with self.q.mutex:
                self.q.queue.clear()
            self._needs_reset = True

            if self.stream is None:
                self._open_stream()
        elif self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def stop(self):
        self._running = False
        self.set_enabled(False)
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    # -- audio thread / worker ---------------------------------------------
    def _audio_callback(self, indata, frames, time_info, status):
        if self.listening_enabled:
            self.q.put(bytes(indata))

    def _worker(self):
        while self._running:
            try:
                data = self.q.get(timeout=0.1)
            except queue.Empty:
                continue

            if not self.listening_enabled:
                continue

            if self._needs_reset:
                self.rec.Reset()
                self._needs_reset = False

            if self.rec.AcceptWaveform(data):
                text = json.loads(self.rec.Result()).get("text", "").strip().lower()
                if text and self.on_text:
                    self.on_text(text, True)
                if text:
                    print(f"[Vosk Heard]: {text}")
                    if any(w in text for w in DELIVER_WORDS):
                        self._emit_deliver()
            else:
                # Partial result for near-zero-latency triggering
                part_text = json.loads(self.rec.PartialResult()).get("partial", "").strip().lower()
                if part_text and self.on_text:
                    self.on_text(part_text, False)
                if any(w in part_text for w in DELIVER_WORDS):
                    print(f"[Vosk Partial Match]: {part_text}")
                    self._emit_deliver()
                    self.rec.Reset()
