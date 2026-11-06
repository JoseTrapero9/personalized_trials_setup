"""Live battery-tray evaluator for the camera PC (YOLO model + XIMEA camera from live_test.py).

The GUI runs on another PC. Both PCs only need to be on the same network:

  GUI PC  --(LSL "ParadigmMarkers": subject, condition, rounds, deliver, handover...)-->  camera PC
  GUI PC  <--(LSL "BatteryEvaluator": predictions + final verdict per round)-----------  camera PC

What it does every round
  1. Follows the GUI phases from the markers and mirrors its timers (retrieval pause, assembly
     countdown 15 / 20 / 25 s, delivery window, overtime). Marker times are converted to this PC's
     clock with LSL time correction, so the countdown matches the GUI screen.
  2. Looks up the expected answer in log_files/sXX_<condition>.txt (the same file the GUI shows,
     round N = piece N) and checks it against the sum + instruction the GUI really displayed.
  3. Reads the tray with the YOLO model. A reading only counts once it is stable for
     STABLE_FRAMES frames without a hand in view.
  4. Predicts while the participant builds: on_track / off_track / correct / wrong
     (Eval_Prediction_... messages, recorded in the XDF file, shown on screen).
  5. At the handover it sends the verdict (Eval_Verdict_Round_<r>_correct|incorrect_...).
     The GUI applies it like the researcher's y / c keys (the first one counts).
  6. Writes logs/evaluator_<subject>_<condition>_<time>.csv (expected vs read, verdict, the
     researcher's own evaluation if given, when the tray first became correct, ...).

Run on the camera PC (from this folder, with the repo's log_files/ next to it):
    python live_evaluator.py                       # camera + YOLO + LSL
    python live_evaluator.py --no-camera           # only follow the GUI (test the network link)
    python live_evaluator.py --subject 3 --condition audio   # if started after the GUI setup screen

Needs: pylsl, plus everything live_test.py needs (ultralytics, torch, opencv, XIMEA API).
"""

import argparse
import csv
import itertools
import os
import queue
import re
import threading
import time

from config import (
    DELIVERY_WINDOW_SECONDS,
    EVALUATOR_STREAM_NAME,
    RETRIEVAL_SECONDS,
    TRAINING_MARKER_PREFIX,
    WARNING_SECONDS,
    assembly_seconds,
    base_dir,
)
from sequences import sequence_path, subject_tag

# ================= CONFIGURATION =================
MARKER_STREAM_NAME = "ParadigmMarkers"     # the GUI's marker stream (lsl_markers.py)
STABLE_FRAMES = 8                          # same tray reading this many frames in a row (~0.27 s at 30 fps)
PARTIAL_COUNTS_AS_INCORRECT = False        # handover with <3 batteries read: True = incorrect, False = no verdict
SEND_VERDICTS = True                       # False = only predict / log, the researcher evaluates with y / c
# =================================================

COLOR_VALUES = {"Blue": 1, "Red": 2, "Yellow": 3, "Green": 4}
SLOT_MULTIPLIERS = (1, 2, 3)


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------
def slot_sum(slots):
    return sum(COLOR_VALUES.get(c, 0) * m for c, m in zip(slots, SLOT_MULTIPLIERS) if c)


def answer_from_instruction(target_sum, instruction):
    """'Use 2 Red and 1 Yellow' + 15 -> ('Red', 'Red', 'Yellow'); None if not exactly one order fits."""
    counts = re.findall(r"(\d+)\s+(blue|red|yellow|green)", instruction or "", re.I)
    colors = []
    for n, c in counts:
        colors += [c.capitalize()] * int(n)
    if len(colors) != 3:
        return None
    fits = {o for o in itertools.permutations(colors) if slot_sum(o) == target_sum}
    return fits.pop() if len(fits) == 1 else None


def load_answer_key(path):
    """Rows of a log file: [{'piece', 'sum', 'instruction', 'answer'}] (answer is a tuple of colors)."""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            parts = [p.strip() for p in line.rstrip("\n").split("\t")]
            if len(parts) < 4 or not parts[0].isdigit():
                continue
            answer = tuple(a.strip().capitalize() for a in parts[3].split(",") if a.strip())
            rows.append({"piece": int(parts[0]), "sum": int(parts[1]), "instruction": parts[2], "answer": answer})
    return rows


def fmt_slots(slots):
    return "-".join(c or "None" for c in slots) if slots else "None"


# ---------------------------------------------------------------------------
# Round / session tracking (pure logic: driven by markers and tray readings)
# ---------------------------------------------------------------------------
class RoundRecord:
    def __init__(self, number, start, duration):
        self.number = number
        self.start = start
        self.deadline = start + duration
        self.target_sum = None
        self.instruction = ""
        self.task_info = ""
        self.expected = None
        self.expected_source = ""
        self.stable_slots = None
        self.prediction = "waiting"
        self.first_correct = None
        self.deliver_times = []
        self.overtime = False
        self.handover = None
        self.point = None
        self.verdict = ""
        self.gui_status = ""
        self.gui_source = ""


class ParadigmTracker:
    def __init__(self, clock, send, subject=None, condition=None, stable_frames=STABLE_FRAMES, log_dir=None):
        self.clock = clock
        self.send = send
        self.subject = subject
        self.condition = condition
        self.stable_frames = stable_frames
        self.training = False
        self.answer_key = None
        self.answer_file = ""
        self.phase = "IDLE"
        self.phase_deadline = None
        self.round = None
        self.last_round = None
        self.notes = []
        self.log_dir = log_dir or os.path.join(base_dir, "logs")
        self.csv_path = None
        self._candidate = None
        self._candidate_count = 0
        self.live_slots = None
        self.hand = False
        self.tray = False
        if subject and condition:
            self._load_answer_key_for(subject, condition)

    # ---------------- markers ----------------
    def handle_marker(self, marker, ts=None):
        ts = self.clock() if ts is None else ts
        self.training = marker.startswith(TRAINING_MARKER_PREFIX)
        m = marker[len(TRAINING_MARKER_PREFIX):] if self.training else marker

        if (r := re.match(r"^Setup_Complete_Subj_(.+?)_Cond_(.+?)_Lang_", m)):
            self.subject, self.condition = r.group(1), r.group(2)
            self._note(f"Setup: subject {self.subject}, condition {self.condition}")
        elif (r := re.match(r"^Condition_Start_(.+)$", m)):
            self._finish_round()
            self.condition = r.group(1)
            self.csv_path = None
            self.phase, self.phase_deadline = "PLAY", None
            self._load_answer_key_for(self.subject, self.condition)
        elif (r := re.match(r"^Sequence_File_(.+)$", m)):
            name = r.group(1)
            path = os.path.join(base_dir, "log_files", name)
            if name.endswith(".txt") and os.path.exists(path):
                self._set_answer_key(path)
            elif name.endswith(".txt"):
                self._note(f"GUI uses {name} but it is not in log_files/ here - answers from the GUI markers")
                self.answer_key, self.answer_file = None, ""
            else:
                self.answer_key, self.answer_file = None, ""
                self._note(f"GUI sequence: {name} - answers from the GUI markers")
        elif (r := re.match(r"^Checkpoint_Retrieval_Start_Round_(\d+)", m)):
            self.phase, self.phase_deadline = "RETRIEVAL", ts + RETRIEVAL_SECONDS
        elif (r := re.match(r"^Dual_Workpiece_Task_Started_Round_(\d+)_Type_(.*)$", m)):
            self._start_round(int(r.group(1)), r.group(2), ts)
        elif (r := re.match(r"^Voice_Deliver_Activated_Round_(\d+)", m)):
            if self.round:
                self.round.deliver_times.append(ts)
                self._note(f"Deliver said - prediction: {self.round.prediction.upper()}")
            self.phase, self.phase_deadline = "DELIVERY", ts + DELIVERY_WINDOW_SECONDS
        elif m.startswith("Delivery_Window_Expired"):
            self.phase, self.phase_deadline = "ASSEMBLY", None
        elif m.startswith("Workpiece_Task_Overtime_System_Failed_Started"):
            if self.round:
                self.round.overtime = True
        elif (r := re.match(r"^Handover_Confirmed_Point_(\d+)_Duration_([\d.]+)", m)):
            self._handover(int(r.group(1)), ts)
        elif (r := re.match(r"^Assembly_Evaluated_(correct|incorrect)", m)):
            rec = self.round or self.last_round
            if rec:
                rec.gui_status = r.group(1)
        elif (r := re.match(r"^Assembly_Evaluation_Source_(.+?)_Round_(\d+)", m)):
            rec = self.round or self.last_round
            if rec and rec.number == int(r.group(2)):
                rec.gui_source = r.group(1)
        elif m.startswith("Condition_Complete_"):
            self.phase, self.phase_deadline = "DONE", None
        elif m in ("Returned_To_Main_Menu", "Application_Closing"):
            self._finish_round()
            self.phase, self.phase_deadline = "IDLE", None

    def _load_answer_key_for(self, subject, condition):
        path = sequence_path(subject, condition) if subject and condition else None
        if path and os.path.exists(path):
            self._set_answer_key(path)
        else:
            self.answer_key, self.answer_file = None, ""

    def _set_answer_key(self, path):
        self.answer_key = load_answer_key(path)
        self.answer_file = os.path.basename(path)
        self._note(f"Answer key: {self.answer_file} ({len(self.answer_key)} pieces)")

    def _start_round(self, number, type_info, ts):
        self._finish_round()
        scenario = "baseline" if (self.condition in (None, "training")) else self.condition
        rec = RoundRecord(number, ts, assembly_seconds(scenario))
        rec.task_info = type_info
        self.round = rec
        self.phase, self.phase_deadline = "ASSEMBLY", None
        self._candidate, self._candidate_count = None, 0

        r = re.match(r"^sum_(\d+)_(.*)$", type_info)
        if not r:
            rec.expected_source = "none (image task)"
            self._note(f"Round {number}: image task {type_info} - no automatic verdict")
            return
        rec.target_sum, rec.instruction = int(r.group(1)), r.group(2).strip()
        from_marker = answer_from_instruction(rec.target_sum, rec.instruction)

        row = None
        if self.answer_key:
            row = self.answer_key[(number - 1) % len(self.answer_key)]   # same indexing as the GUI
        if row and row["sum"] == rec.target_sum and row["instruction"].lower() == rec.instruction.lower() \
                and slot_sum(row["answer"]) == rec.target_sum:
            rec.expected, rec.expected_source = row["answer"], f"{self.answer_file} piece {row['piece']}"
        else:
            if row:
                self._note(f"WARNING round {number}: {self.answer_file} piece {row['piece']} says "
                           f"{row['sum']} / {row['instruction']} but GUI shows {rec.target_sum} / {rec.instruction}")
                self.send(f"Eval_Log_Mismatch_Round_{number}_File_{self.answer_file}")
            rec.expected, rec.expected_source = from_marker, "GUI marker"
        self._note(f"Round {number}: sum {rec.target_sum}, {rec.instruction} -> {fmt_slots(rec.expected)} "
                   f"({rec.expected_source})")

    def _handover(self, point, ts):
        rec = self.round
        if rec is None:
            return
        rec.handover, rec.point = ts, point
        self.phase, self.phase_deadline = "PLAY", None

        slots = rec.stable_slots
        filled = sum(1 for c in slots if c) if slots else 0
        if rec.expected is None or slots is None:
            verdict, reason = "", "no_expected_answer" if rec.expected is None else "no_stable_reading"
        elif filled == 3:
            verdict, reason = ("correct" if tuple(slots) == tuple(rec.expected) else "incorrect"), ""
        elif PARTIAL_COUNTS_AS_INCORRECT:
            verdict, reason = "incorrect", ""
        else:
            verdict, reason = "", f"only_{filled}_batteries_read"

        rec.verdict = verdict or "none"
        if verdict and SEND_VERDICTS:
            self.send(f"Eval_Verdict_Round_{rec.number}_{verdict}_Slots_{fmt_slots(slots)}_Sum_{slot_sum(slots)}"
                      f"_Expected_{fmt_slots(rec.expected)}_Target_{rec.target_sum}")
        elif verdict:
            self.send(f"Eval_Result_Round_{rec.number}_{verdict}_Slots_{fmt_slots(slots)}")
        else:
            self.send(f"Eval_NoVerdict_Round_{rec.number}_{reason}")
        self._note(f"Round {rec.number} handover -> {rec.verdict.upper()} "
                   f"(read {fmt_slots(slots)}, expected {fmt_slots(rec.expected)}){' ' + reason if reason else ''}")
        self.last_round, self.round = rec, None

    # ---------------- tray readings ----------------
    def update_reading(self, slots, hand, tray_seen, ts=None):
        ts = self.clock() if ts is None else ts
        self.hand, self.tray = hand, tray_seen
        if hand or not tray_seen:
            self._candidate, self._candidate_count = None, 0
            return
        slots = tuple(slots)
        self.live_slots = slots
        if slots == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate, self._candidate_count = slots, 1
        rec = self.round
        if rec is None or self._candidate_count != self.stable_frames:
            return
        # a new stable reading during this round
        rec.stable_slots = slots
        prediction = self._predict(slots, rec.expected)
        if rec.first_correct is None and prediction == "correct":
            rec.first_correct = ts
        rec.prediction = prediction
        self.send(f"Eval_Prediction_Round_{rec.number}_{prediction}_Slots_{fmt_slots(slots)}"
                  f"_Sum_{slot_sum(slots)}_Target_{rec.target_sum}")

    @staticmethod
    def _predict(slots, expected):
        filled = [c for c in slots if c]
        if not filled:
            return "empty"
        if expected is None:
            return "unknown"
        if len(filled) == 3:
            return "correct" if tuple(slots) == tuple(expected) else "wrong"
        mismatch = any(c and c != e for c, e in zip(slots, expected))
        return "off_track" if mismatch else "on_track"

    # ---------------- logging ----------------
    def _finish_round(self):
        rec = self.last_round
        if rec is None:
            return
        self.last_round = None
        if self.training:
            return
        os.makedirs(self.log_dir, exist_ok=True)
        if self.csv_path is None:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            self.csv_path = os.path.join(
                self.log_dir, f"evaluator_{subject_tag(self.subject)}_{self.condition}_{stamp}.csv")
        new = not os.path.exists(self.csv_path)
        rel = (lambda t: "" if t is None else round(t - rec.start, 3))
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["subject", "condition", "round", "target_sum", "instruction", "expected",
                            "expected_source", "read_slots", "read_sum", "verdict", "gui_status", "gui_source",
                            "agrees_with_gui", "first_correct_s", "first_deliver_s", "deliver_count",
                            "handover_s", "correct_before_deliver", "overtime", "point"])
            first_deliver = rec.deliver_times[0] if rec.deliver_times else None
            w.writerow([
                self.subject, self.condition, rec.number, rec.target_sum, rec.instruction,
                fmt_slots(rec.expected), rec.expected_source, fmt_slots(rec.stable_slots),
                slot_sum(rec.stable_slots) if rec.stable_slots else "", rec.verdict, rec.gui_status,
                rec.gui_source,
                "" if not (rec.gui_status and rec.verdict in ("correct", "incorrect")) else rec.gui_status == rec.verdict,
                rel(rec.first_correct), rel(first_deliver), len(rec.deliver_times), rel(rec.handover),
                rec.first_correct is not None and (first_deliver is None or rec.first_correct <= first_deliver),
                rec.overtime, rec.point,
            ])

    def close(self):
        if self.round is not None:
            self.last_round, self.round = self.round, None
        self._finish_round()

    # ---------------- display ----------------
    def _note(self, text):
        print(f"[EVAL] {text}")
        self.notes = (self.notes + [text])[-4:]

    def timer_text(self, now=None):
        now = self.clock() if now is None else now
        rec = self.round
        if self.phase == "RETRIEVAL" and self.phase_deadline:
            return f"RETRIEVAL  {max(0, self.phase_deadline - now):.0f} s"
        if self.phase in ("ASSEMBLY", "DELIVERY") and rec:
            left = rec.deadline - now
            text = f"ASSEMBLY  {left:.0f} s" if left > 0 else f"OVERTIME  +{-left:.0f} s"
            if left > 0 and left <= WARNING_SECONDS:
                text += "  (warning)"
            if self.phase == "DELIVERY" and self.phase_deadline:
                text += f"  |  DELIVERY WINDOW {max(0, self.phase_deadline - now):.0f} s"
            return text
        return {"IDLE": "WAITING FOR GUI", "PLAY": "RADIO GAME (to checkpoint)", "DONE": "CONDITION DONE"}.get(
            self.phase, self.phase)

    def hud_lines(self, now=None):
        rec = self.round or self.last_round
        lines = [
            f"{subject_tag(self.subject) if self.subject else 's??'}  {self.condition or '?'}"
            f"{'  [TRAINING]' if self.training else ''}  key: {self.answer_file or '-'}",
            self.timer_text(now),
        ]
        if rec:
            lines.append(f"Round {rec.number}: sum {rec.target_sum}  {rec.instruction}")
            lines.append(f"Expected: {fmt_slots(rec.expected)}")
            lines.append(f"Read:     {fmt_slots(rec.stable_slots)}"
                         f"{'  sum ' + str(slot_sum(rec.stable_slots)) if rec.stable_slots else ''}")
            lines.append(f"Prediction: {rec.prediction.upper()}"
                         + (f"   Verdict: {rec.verdict.upper()}" if rec.verdict else ""))
        if self.hand:
            lines.append("hand in view - holding last reading")
        elif not self.tray:
            lines.append("no tray in view")
        return lines


# ---------------------------------------------------------------------------
# LSL plumbing
# ---------------------------------------------------------------------------
class MarkerListener(threading.Thread):
    """Receives the GUI markers; timestamps are converted to this PC's LSL clock."""

    def __init__(self, out_queue, stream_name=MARKER_STREAM_NAME):
        super().__init__(daemon=True)
        self.out_queue = out_queue
        self.stream_name = stream_name
        self.running = True
        self.connected = False

    def run(self):
        import pylsl
        lost_error = getattr(pylsl, "LostError", None) or pylsl.util.LostError
        timeout_error = getattr(pylsl, "TimeoutError", None) or pylsl.util.TimeoutError
        while self.running:
            streams = pylsl.resolve_byprop("name", self.stream_name, 1, 1.0)
            if not streams:
                continue
            inlet = pylsl.StreamInlet(streams[0], max_buflen=360, recover=False)
            print(f"[LSL] Connected to GUI markers on {streams[0].hostname()}")
            self.connected = True
            correction, last_corr = 0.0, 0.0
            try:
                while self.running:
                    if time.time() - last_corr > 5.0:
                        try:
                            correction, last_corr = inlet.time_correction(timeout=1.0), time.time()
                        except timeout_error:
                            pass
                    sample, ts = inlet.pull_sample(timeout=0.2)
                    if sample:
                        self.out_queue.put((str(sample[0]), ts + correction))
            except lost_error:
                print("[LSL] GUI marker stream lost - waiting for it to come back...")
            finally:
                self.connected = False


def make_outlet():
    import socket
    import pylsl
    info = pylsl.StreamInfo(EVALUATOR_STREAM_NAME, "Markers", 1, 0, "string",
                            f"battery_evaluator_{socket.gethostname()}")
    outlet = pylsl.StreamOutlet(info)

    def send(msg):
        outlet.push_sample([msg])
        print(f"[SEND] {msg}")
    return send


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------
def drain(q, tracker):
    while True:
        try:
            marker, ts = q.get_nowait()
        except queue.Empty:
            return
        tracker.handle_marker(marker, ts)


def run_without_camera(tracker, q, listener):
    print("[INFO] No camera: following the GUI only. Ctrl+C to stop.")
    last = None
    try:
        while True:
            drain(q, tracker)
            lines = tracker.hud_lines()
            text = " | ".join(lines[:2]) + ("" if listener.connected else "  (GUI not found)")
            if text != last:
                print("[HUD]", text)
                last = text
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass


def run_with_camera(tracker, q, listener):
    import cv2
    import torch
    from ultralytics import YOLO
    from live_test import FPS_XIMEA, MC050_PRESET, MODEL_PATH, CONFIDENCE, XimeaCaptureThread, evaluate_tray_slots

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at: {MODEL_PATH}")
    device = 0 if torch.cuda.is_available() else "cpu"
    model = YOLO(MODEL_PATH)
    print(f"[INFO] YOLO on {device}, classes {model.names}")
    cam = XimeaCaptureThread(MC050_PRESET, fps=FPS_XIMEA)
    cam.start()

    phase_colors = {"ASSEMBLY": (0, 200, 255), "DELIVERY": (255, 160, 0), "RETRIEVAL": (200, 200, 0)}
    pred_colors = {"CORRECT": (0, 220, 0), "WRONG": (0, 0, 255), "OFF_TRACK": (0, 120, 255),
                   "ON_TRACK": (0, 200, 200)}
    try:
        while True:
            drain(q, tracker)
            try:
                frame = cam.frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            results = model.predict(source=frame, conf=CONFIDENCE, device=device, verbose=False)[0]
            status, slots, _ = evaluate_tray_slots(results, model.names)
            # evaluate_tray_slots reports hand / missing tray through its status text
            hand = status.startswith("HAND")
            tray = not status.startswith("WAITING")
            tracker.update_reading(slots, hand, tray)

            preview = cv2.resize(results.plot(), (1024, 576))
            panel = cv2.copyMakeBorder(preview, 0, 0, 0, 470, cv2.BORDER_CONSTANT, value=(25, 25, 25))
            y = 40
            for i, line in enumerate(tracker.hud_lines()):
                color = (230, 230, 230)
                if i == 1:
                    color = (0, 0, 255) if "OVERTIME" in line else phase_colors.get(tracker.phase, color)
                for key, c in pred_colors.items():
                    if line.startswith("Prediction") and key in line.split()[1]:
                        color = c
                cv2.putText(panel, line, (1040, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6 if i else 0.55, color, 2)
                y += 38
            y += 10
            for note in tracker.notes:
                cv2.putText(panel, note[:58], (1040, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 160, 160), 1)
                y += 24
            link = "GUI linked" if listener.connected else "GUI NOT FOUND"
            cv2.putText(panel, link, (1040, 560), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 200, 0) if listener.connected else (0, 0, 255), 2)
            cv2.imshow("Battery evaluator", panel)
            if (cv2.waitKey(1) & 0xFF) in (ord("q"), ord("Q"), 27):
                break
    finally:
        cam.stop()
        cv2.destroyAllWindows()


def main():
    global PARTIAL_COUNTS_AS_INCORRECT, SEND_VERDICTS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", help="subject number, only needed if started after the GUI setup screen")
    ap.add_argument("--condition", help="GUI condition name (baseline, audio, haptic, ...), same as --subject")
    ap.add_argument("--no-camera", action="store_true", help="only follow the GUI markers (link test)")
    ap.add_argument("--stable-frames", type=int, default=STABLE_FRAMES)
    ap.add_argument("--predict-only", action="store_true", help="never send verdicts to the GUI")
    ap.add_argument("--partial-incorrect", action="store_true", help="handover with <3 batteries = incorrect")
    args = ap.parse_args()
    SEND_VERDICTS = SEND_VERDICTS and not args.predict_only
    PARTIAL_COUNTS_AS_INCORRECT = PARTIAL_COUNTS_AS_INCORRECT or args.partial_incorrect

    import pylsl
    send = make_outlet()
    tracker = ParadigmTracker(pylsl.local_clock, send, args.subject, args.condition, args.stable_frames)
    q = queue.Queue()
    listener = MarkerListener(q)
    listener.start()
    send("Eval_Started")
    try:
        if args.no_camera:
            run_without_camera(tracker, q, listener)
        else:
            run_with_camera(tracker, q, listener)
    finally:
        listener.running = False
        tracker.close()
        send("Eval_Stopped")
        if tracker.csv_path:
            print(f"[INFO] Log: {tracker.csv_path}")


if __name__ == "__main__":
    main()
