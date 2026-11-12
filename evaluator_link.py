"""GUI side of the camera evaluator link.

live_evaluator.py runs on the camera PC. It follows the GUI through the ParadigmMarkers LSL
stream (sent by lsl_markers.py) and answers on its own LSL stream (EVALUATOR_STREAM_NAME):

    Eval_Verdict_Round_<r>_<correct|incorrect>_...     -> applied like the researcher's y / c key
    Eval_Battery_Round_<r>_Slot_<k>_<correct|incorrect>_...   -> vest / sound cue for that battery
    Eval_Prediction_Round_<r>_...                      -> live prediction, only recorded (not applied)

LSL finds streams on the local network by itself, so both PCs only need to be on the same
network (no IP addresses to configure). The listener runs in a background thread and
reconnects if the evaluator is restarted.
"""

import re

from PyQt5.QtCore import QThread, pyqtSignal

from config import EVALUATOR_STREAM_NAME

VERDICT_RE = re.compile(r"^Eval_Verdict_Round_(\d+)_(correct|incorrect)(?:_|$)")
BATTERY_RE = re.compile(r"^Eval_Battery_Round_(\d+)_Slot_(\d)_(correct|incorrect)(?:_|$)")


class EvaluatorLink(QThread):
    verdict_received = pyqtSignal(int, bool)      # round, is_correct
    battery_received = pyqtSignal(int, int, bool) # round, slot (1-3), is_correct  -> per-battery cue
    message_received = pyqtSignal(str)            # every evaluator message (for logging)
    connection_changed = pyqtSignal(bool)

    def __init__(self, stream_name=EVALUATOR_STREAM_NAME, parent=None):
        super().__init__(parent)
        self.stream_name = stream_name
        self._running = True

    def stop(self):
        self._running = False
        self.wait(3000)

    def run(self):
        try:
            import pylsl
        except ImportError:
            print("[EvaluatorLink] pylsl not available - camera evaluator disabled.")
            return

        # pylsl >= 1.17 keeps the exception in pylsl.util
        lost_error = getattr(pylsl, "LostError", None) or pylsl.util.LostError

        while self._running:
            streams = pylsl.resolve_byprop("name", self.stream_name, 1, 1.0)
            if not streams:
                continue
            inlet = pylsl.StreamInlet(streams[0], max_buflen=60, recover=False)
            print(f"[EvaluatorLink] Connected to '{self.stream_name}' on {streams[0].hostname()}")
            self.connection_changed.emit(True)
            try:
                while self._running:
                    sample, _ = inlet.pull_sample(timeout=0.5)
                    if not sample:
                        continue
                    msg = str(sample[0])
                    self.message_received.emit(msg)
                    m = BATTERY_RE.match(msg)
                    if m:
                        self.battery_received.emit(int(m.group(1)), int(m.group(2)), m.group(3) == "correct")
                        continue
                    m = VERDICT_RE.match(msg)
                    if m:
                        self.verdict_received.emit(int(m.group(1)), m.group(2) == "correct")
            except lost_error:
                print("[EvaluatorLink] Evaluator stream lost - waiting for it to come back...")
            finally:
                self.connection_changed.emit(False)
                try:
                    inlet.close_stream()
                except Exception:
                    pass
