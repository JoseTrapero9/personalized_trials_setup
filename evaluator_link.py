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
import time

from PyQt5.QtCore import QThread, pyqtSignal

from config import EVALUATOR_STREAM_NAME

VERDICT_RE = re.compile(r"^Eval_Verdict_Round_(\d+)_(correct|incorrect)(?:_|$)")
BATTERY_RE = re.compile(r"^Eval_Battery_Round_(\d+)_Slot_(\d)_(correct|incorrect)(?:_|$)")
CAM_MS_RE = re.compile(r"_CamMs_(\d+)")


class EvaluatorLink(QThread):
    verdict_received = pyqtSignal(int, bool)      # round, is_correct
    # round, slot (1-3), is_correct, camera ms (frame -> message sent, -1 unknown), link ms (sent -> received)
    battery_received = pyqtSignal(int, int, bool, int, int)
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
            timeout_error = getattr(pylsl, "TimeoutError", None) or pylsl.util.TimeoutError
            correction, next_correction = None, 0.0
            try:
                while self._running:
                    if time.monotonic() >= next_correction:        # clock offset between the two PCs
                        try:
                            correction = inlet.time_correction(timeout=0.5)
                        except timeout_error:
                            pass
                        next_correction = time.monotonic() + (10.0 if correction is not None else 2.0)
                    sample, ts = inlet.pull_sample(timeout=0.5)
                    if not sample:
                        continue
                    msg = str(sample[0])
                    m = BATTERY_RE.match(msg)
                    if m:
                        link_ms = -1 if correction is None else int(round((pylsl.local_clock() - (ts + correction)) * 1000))
                        cam = CAM_MS_RE.search(msg)
                        self.battery_received.emit(int(m.group(1)), int(m.group(2)), m.group(3) == "correct",
                                                   int(cam.group(1)) if cam else -1, link_ms)
                        self.message_received.emit(msg)
                        continue
                    self.message_received.emit(msg)
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
