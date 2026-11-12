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
    VOICE_KEEP_MIC_OPEN,
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

    def __init__(self):
        super().__init__()
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
            return

        if not os.path.exists(VOSK_MODEL_DIR):
            print(f"Vosk model folder not found at '{VOSK_MODEL_DIR}'. "
                  f"Voice recognition disabled (use 'D' key fallback).")
            return

        try:
            print("Loading offline Vosk speech model...")
            self.model = Model(VOSK_MODEL_DIR)
            # Grammar restriction: lock recognition to the trigger words only
            grammar = json.dumps(list(DELIVER_WORDS) + ["[unk]"])
            self.rec = KaldiRecognizer(self.model, VOSK_SAMPLE_RATE, grammar)
            self.vosk_ready = True
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            print("Vosk speech recognition active and ready.")
        except Exception as e:
            print(f"Failed to initialize Vosk model: {e}")
            self.vosk_ready = False

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _find_input_device():
        if not VOICE_INPUT_KEYWORD:
            return None
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and VOICE_INPUT_KEYWORD.lower() in d["name"].lower():
                print(f"Voice input set to Device {i}: {d['name']}")
                return i
        print(f"Input device '{VOICE_INPUT_KEYWORD}' not found, using system default.")
        return None

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

            self.open_microphone()
        elif not VOICE_KEEP_MIC_OPEN:
            self.close_microphone()
        # with VOICE_KEEP_MIC_OPEN the stream stays open; audio is simply ignored while not listening

    def open_microphone(self):
        """Open the microphone stream (does nothing if it is already open). Listening is switched
        separately with set_enabled()."""
        if not self.vosk_ready or self.stream is not None:
            return
        try:
            self.stream = sd.InputStream(
                device=self._find_input_device(),
                samplerate=VOSK_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                callback=self._audio_callback,
            )
            self.stream.start()
        except Exception as e:
            self.stream = None
            print(f"Failed to start microphone stream for Vosk: {e}")

    def close_microphone(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def stop(self):
        self._running = False
        self.listening_enabled = False
        self.close_microphone()
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
                if text:
                    print(f"[Vosk Heard]: {text}")
                    if any(w in text for w in DELIVER_WORDS):
                        self._emit_deliver()
            else:
                # Partial result for near-zero-latency triggering
                part_text = json.loads(self.rec.PartialResult()).get("partial", "").strip().lower()
                if any(w in part_text for w in DELIVER_WORDS):
                    print(f"[Vosk Partial Match]: {part_text}")
                    self._emit_deliver()
                    self.rec.Reset()
