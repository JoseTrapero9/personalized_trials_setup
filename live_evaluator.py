"""Live battery-tray evaluator for the camera PC (YOLO model + XIMEA camera from live_test.py).

Two modes
---------
TEST (no GUI needed, run it right now):
    python live_evaluator.py --test                    # pick a log file in a window
    python live_evaluator.py --test s03_audio          # or name it (log_files/s03_audio.txt)
    python live_evaluator.py --test s03_audio --webcam 0   # test with a normal webcam instead of the XIMEA
    python live_evaluator.py --test s03_audio --mic Bose   # use the microphone whose name contains "Bose"
  Row 1 of the file is active right away. Build the tray: every battery gets a check or a cross
  in the table as soon as the camera sees it. Say "deliver" (or press D) to evaluate the row and
  move on to the next one. R = redo the current row, Q / Esc = quit.

LIVE (with the GUI on the other PC, same network):
    python live_evaluator.py
    python live_evaluator.py --no-camera     # only follow the GUI (test the network link)

  GUI PC  --(LSL "ParadigmMarkers": subject, condition, rounds, deliver, handover...)-->  camera PC
  GUI PC  <--(LSL "BatteryEvaluator": predictions + verdict per round)----------------  camera PC

How a row / round is evaluated (both modes)
  * Evaluation is ACTIVE (marks drawn in green) from the start of the round until it is evaluated;
    afterwards the marks are frozen and drawn in black.
  * A tray reading counts once it is the same for STABLE_FRAMES frames with no hand at the station.
  * Only the STATION counts (the model's "Station" class): batteries are read only inside a tray
    whose centre is on the station. Batteries lying around (dropped on the table / floor), trays
    elsewhere and hands away from the station are ignored. The station box is remembered, so it
    still works while the tray covers the station.
  * The round is evaluated at the FIRST of:
      - the tray is off the station (no tray on it and no hand at it for TRAY_GONE_SECONDS),
        so a participant who says "deliver" after picking the tray up is still judged on the
        tray as it was on the station;
      - "deliver" is said;
      - the handover (live mode, if nothing happened before).
  * Correct only if all 3 slots match the answer of the log file. A slot that is not seen counts
    as wrong, so fewer than 3 batteries in view = mistake. There is no manual evaluation any more.
  * The tray from the previous round does not count: tray-leaves-station is only armed after the
    station was cleared (or the tray changed) during this round.
  * Live mode: the verdict is sent to the GUI (Eval_Verdict_Round_<r>_correct|incorrect_..._Trigger_...)
    and applied there right away. The answer table on screen is the subject's log file.

Writes logs/evaluator_<subject>_<condition>_<time>.csv (test mode: evaluator_test_<file>_<time>.csv).
Needs: pylsl (live mode) and everything live_test.py needs (ultralytics, torch, opencv, XIMEA API).
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
    MAX_ROUNDS_PER_CONDITION,
    RETRIEVAL_SECONDS,
    TRAINING_MARKER_PREFIX,
    VOICE_COOLDOWN_SECONDS,
    WARNING_SECONDS,
    assembly_seconds,
    base_dir,
)
from sequences import sequence_path, subject_tag

# ================= CONFIGURATION =================
MARKER_STREAM_NAME = "ParadigmMarkers"     # the GUI's marker stream (lsl_markers.py)
STABLE_FRAMES = 8                          # same tray reading this many frames in a row (~0.27 s at 30 fps)
TRAY_GONE_SECONDS = 0.5                    # tray off the station (no hand at it) this long -> evaluate
STATION_CLEAR_SECONDS = 0.3                # no tray on the station this long = cleared (arms "tray left")
STATION_LABEL = "station"                  # YOLO class of the assembly station (case-insensitive)
STATION_MARGIN = 0.10                      # tray centre may be this fraction of the station size outside it
SEND_VERDICTS = True                       # False = only predict / log (--predict-only)
# =================================================

COLOR_VALUES = {"Blue": 1, "Red": 2, "Yellow": 3, "Green": 4}
SLOT_MULTIPLIERS = (1, 2, 3)
EMPTY = (None, None, None)


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


def slot_marks(slots, expected):
    """Per slot: None = nothing there, True = right color, False = wrong color."""
    return [None if s is None else s == e for s, e in zip(slots, expected)]


# ---------------------------------------------------------------------------
# Round / session tracking (pure logic: driven by markers or keys, and tray readings)
# ---------------------------------------------------------------------------
class RoundRecord:
    def __init__(self, number, start, duration=None):
        self.number = number
        self.row = None                 # index in the table
        self.start = start
        self.deadline = None if duration is None else start + duration
        self.target_sum = None
        self.instruction = ""
        self.expected = None
        self.expected_source = ""
        self.active = True              # evaluation running (green marks)
        self.armed = False              # station cleared / tray changed since the round started
        self.tray_seen = False          # a tray was read on the station after arming
        self.stable_slots = None
        self.prediction = "waiting"
        self.first_correct = None
        self.deliver_times = []
        self.overtime = False
        self.handover = None
        self.point = None
        self.verdict = ""
        self.trigger = ""
        self.eval_time = None
        self.final_slots = None
        self.gui_status = ""
        self.gui_source = ""


class ParadigmTracker:
    def __init__(self, clock, send, subject=None, condition=None, stable_frames=STABLE_FRAMES,
                 log_dir=None, mode="live"):
        self.clock = clock
        self.send = send
        self.mode = mode                # "live" (follows the GUI) | "test" (keys / voice)
        self.subject = subject
        self.condition = condition
        self.stable_frames = stable_frames
        self.training = False
        self.answer_file = ""
        self.table = []                 # rows: piece, sum, instruction, answer, marks, result, used
        self.phase = "IDLE"
        self.phase_deadline = None
        self.round = None
        self.last_round = None
        self.prev_final = None          # tray of the previous evaluated round
        self.finished = False
        self.notes = []
        self.log_dir = log_dir or os.path.join(base_dir, "logs")
        self.csv_path = None
        self._candidate = None
        self._candidate_count = 0
        self._absent_since = None
        self.live_slots = None
        self.hand = False
        self.tray = False
        self.camera_detail = ""         # e.g. "tray off the station", "STATION NOT FOUND"
        if subject and condition:
            self._load_answer_key_for(subject, condition)

    # ---------------- answer table ----------------
    def _load_answer_key_for(self, subject, condition):
        path = sequence_path(subject, condition) if subject and condition else None
        if path and os.path.exists(path):
            self._set_answer_key(path)
        else:
            self.table, self.answer_file = [], ""

    def _set_answer_key(self, path):
        key = load_answer_key(path)
        used = len(key) if self.mode == "test" else MAX_ROUNDS_PER_CONDITION
        self.table = [dict(r, marks=[None] * 3, result="", used=i < used) for i, r in enumerate(key)]
        self.answer_file = os.path.basename(path)
        self._note(f"Answer key: {self.answer_file} ({len(key)} pieces)")

    # ---------------- GUI markers (live mode) ----------------
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
            self.csv_path, self.round, self.prev_final = None, None, None
            self.phase, self.phase_deadline = "PLAY", None
            self._load_answer_key_for(self.subject, self.condition)
        elif (r := re.match(r"^Sequence_File_(.+)$", m)):
            name = r.group(1)
            path = os.path.join(base_dir, "log_files", name)
            if name.endswith(".txt") and os.path.exists(path):
                if name != self.answer_file:
                    self._set_answer_key(path)
            else:
                self.table, self.answer_file = [], ""
                self._note(f"GUI sequence: {name} - answers taken from the GUI markers")
        elif re.match(r"^Checkpoint_Retrieval_Start_Round_(\d+)", m):
            self.phase, self.phase_deadline = "RETRIEVAL", ts + RETRIEVAL_SECONDS
        elif (r := re.match(r"^Dual_Workpiece_Task_Started_Round_(\d+)_Type_(.*)$", m)):
            number, info = int(r.group(1)), r.group(2)
            scenario = "baseline" if self.condition in (None, "training") else self.condition
            s = re.match(r"^sum_(\d+)_(.*)$", info)
            if s:
                self._start_round(number, int(s.group(1)), s.group(2).strip(), ts, assembly_seconds(scenario))
            else:
                self._start_round(number, None, info, ts, assembly_seconds(scenario))
            self.phase, self.phase_deadline = "ASSEMBLY", None
        elif re.match(r"^Voice_Deliver_Activated_Round_(\d+)", m):
            if self.round:
                self.round.deliver_times.append(ts)
                self.evaluate("deliver", ts)
            self.phase, self.phase_deadline = "DELIVERY", ts + DELIVERY_WINDOW_SECONDS
        elif m.startswith("Delivery_Window_Expired"):
            self.phase, self.phase_deadline = "ASSEMBLY", None
        elif m.startswith("Workpiece_Task_Overtime_System_Failed_Started"):
            if self.round:
                self.round.overtime = True
        elif (r := re.match(r"^Handover_Confirmed_Point_(\d+)_Duration_([\d.]+)", m)):
            rec = self.round
            if rec:
                self.evaluate("handover", ts)
                rec.handover, rec.point = ts, int(r.group(1))
                self.last_round, self.round = rec, None
            self.phase, self.phase_deadline = "PLAY", None
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
            self.round = None
            self.phase, self.phase_deadline = "IDLE", None

    # ---------------- test mode (keys / voice) ----------------
    def start_test(self, path):
        self.mode = "test"
        self.subject = "test"
        self.condition = os.path.splitext(os.path.basename(path))[0]
        self._set_answer_key(path)
        self.phase = "TEST"
        self.start_row(0)

    def start_row(self, idx, ts=None):
        ts = self.clock() if ts is None else ts
        row = self.table[idx]
        self._start_round(idx + 1, row["sum"], row["instruction"], ts, None)

    def deliver(self, ts=None):
        """Test mode: 'deliver' evaluates the row (if the tray did not leave already) and moves on."""
        ts = self.clock() if ts is None else ts
        rec = self.round
        if rec is None or self.finished:
            return
        rec.deliver_times.append(ts)
        self.evaluate("deliver", ts)
        self.last_round, self.round = rec, None
        if rec.number < len(self.table):
            self.start_row(rec.number, ts)
        else:
            self._finish_round()
            self.finished = True
            self.phase = "DONE"
            self._note("Test finished - all rows evaluated. Press Q to close.")

    def redo_row(self, ts=None):
        if self.round is not None:
            self.start_row(self.round.number - 1, ts)

    # ---------------- rounds ----------------
    def _start_round(self, number, target_sum, instruction, ts, duration):
        self._finish_round()
        rec = RoundRecord(number, ts, duration)
        rec.target_sum, rec.instruction = target_sum, instruction
        self.round = rec
        self._candidate, self._candidate_count = None, 0

        if target_sum is None:
            rec.active = False
            rec.expected_source = "none (image task)"
            self._note(f"Round {number}: image task {instruction} - not evaluated")
            return

        from_marker = answer_from_instruction(target_sum, instruction)
        row = self.table[(number - 1) % len(self.table)] if self.table else None
        if row and row["sum"] == target_sum and row["instruction"].lower() == instruction.lower() \
                and slot_sum(row["answer"]) == target_sum:
            rec.expected, rec.expected_source = row["answer"], f"{self.answer_file} piece {row['piece']}"
        else:
            if row:
                self._note(f"WARNING round {number}: {self.answer_file} piece {row['piece']} says "
                           f"{row['sum']} / {row['instruction']}, GUI shows {target_sum} / {instruction}")
                self.send(f"Eval_Log_Mismatch_Round_{number}_File_{self.answer_file}")
                row.update(sum=target_sum, instruction=instruction, answer=from_marker or ("?", "?", "?"))
            else:
                # no answer file (training / missing): build the table from what the GUI shows
                self.table.append({"piece": number, "sum": target_sum, "instruction": instruction,
                                   "answer": from_marker or ("?", "?", "?"), "used": True})
                row = self.table[-1]
            rec.expected, rec.expected_source = from_marker, "GUI marker"
        row.update(marks=[None] * 3, result="")
        rec.row = self.table.index(row)
        self._note(f"Round {number}: sum {target_sum}, {instruction} -> {fmt_slots(rec.expected)}")

    def evaluate(self, trigger, ts=None):
        """Final verdict of the active round. Slots not seen count as wrong."""
        ts = self.clock() if ts is None else ts
        rec = self.round
        if rec is None or not rec.active:
            return
        rec.active = False
        rec.trigger, rec.eval_time = trigger, ts
        if rec.expected is None:
            rec.verdict = "none"
            self.send(f"Eval_NoVerdict_Round_{rec.number}_no_expected_answer")
            return
        slots = tuple(rec.stable_slots) if rec.stable_slots else EMPTY
        marks = [s is not None and s == e for s, e in zip(slots, rec.expected)]
        rec.final_slots = slots
        rec.verdict = "correct" if all(marks) else "incorrect"
        self.prev_final = slots
        if rec.row is not None:
            self.table[rec.row].update(marks=marks, result=rec.verdict)

        msg = (f"Round_{rec.number}_{rec.verdict}_Slots_{fmt_slots(slots)}_Sum_{slot_sum(slots)}"
               f"_Expected_{fmt_slots(rec.expected)}_Target_{rec.target_sum}_Trigger_{trigger}")
        self.send(("Eval_Verdict_" if (self.mode == "live" and SEND_VERDICTS) else "Eval_Result_") + msg)
        self._note(f"Round {rec.number}: {rec.verdict.upper()} ({trigger.replace('_', ' ')}) "
                   f"read {fmt_slots(slots)}, expected {fmt_slots(rec.expected)}")

    # ---------------- tray readings ----------------
    def update_reading(self, slots, hand, tray_seen, ts=None, detail=""):
        """slots: tray on the station; hand: hand at the station; tray_seen: a tray is ON the station."""
        ts = self.clock() if ts is None else ts
        self.hand, self.tray, self.camera_detail = hand, tray_seen, detail
        if hand:
            self._candidate, self._candidate_count, self._absent_since = None, 0, None
            return
        if not tray_seen:
            self._candidate, self._candidate_count = None, 0
            self.live_slots = None
            if self._absent_since is None:
                self._absent_since = ts
            self._check_station(ts)
            return
        self._absent_since = None
        slots = tuple(slots)
        self.live_slots = slots
        if slots == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate, self._candidate_count = slots, 1
        if self._candidate_count == self.stable_frames:
            self._on_stable(slots, ts)

    def _check_station(self, ts):
        rec = self.round
        if rec is None or not rec.active:
            return
        gone = ts - self._absent_since
        if not rec.armed and gone >= STATION_CLEAR_SECONDS:
            rec.armed = True
        if rec.armed and rec.tray_seen and gone >= TRAY_GONE_SECONDS:
            self.evaluate("tray_left", ts)

    def _on_stable(self, slots, ts):
        rec = self.round
        if rec is None or not rec.active:
            return
        if not rec.armed and (slots == EMPTY or slots != self.prev_final):
            rec.armed = True        # empty tray, or not the previous round's tray any more
        rec.stable_slots = slots
        if not rec.armed or rec.expected is None:
            return
        rec.tray_seen = True
        marks = slot_marks(slots, rec.expected)
        if rec.row is not None:
            self.table[rec.row]["marks"] = marks
        filled = [m for m in marks if m is not None]
        if not filled:
            prediction = "empty"
        elif len(filled) == 3:
            prediction = "correct" if all(filled) else "wrong"
        else:
            prediction = "on_track" if all(filled) else "off_track"
        if prediction == "correct" and rec.first_correct is None:
            rec.first_correct = ts
        rec.prediction = prediction
        self.send(f"Eval_Prediction_Round_{rec.number}_{prediction}_Slots_{fmt_slots(slots)}"
                  f"_Sum_{slot_sum(slots)}_Target_{rec.target_sum}")

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
            name = (f"evaluator_test_{self.condition}_{stamp}.csv" if self.mode == "test"
                    else f"evaluator_{subject_tag(self.subject)}_{self.condition}_{stamp}.csv")
            self.csv_path = os.path.join(self.log_dir, name)
        new = not os.path.exists(self.csv_path)
        rel = (lambda t: "" if t is None else round(t - rec.start, 3))
        first_deliver = rec.deliver_times[0] if rec.deliver_times else None
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["subject", "condition", "round", "target_sum", "instruction", "expected",
                            "expected_source", "read_slots", "read_sum", "verdict", "trigger", "eval_s",
                            "first_correct_s", "first_deliver_s", "deliver_count", "handover_s",
                            "correct_before_deliver", "overtime", "point", "gui_status", "gui_source"])
            w.writerow([
                self.subject, self.condition, rec.number, rec.target_sum, rec.instruction,
                fmt_slots(rec.expected), rec.expected_source, fmt_slots(rec.final_slots),
                slot_sum(rec.final_slots) if rec.final_slots else "", rec.verdict or "none", rec.trigger,
                rel(rec.eval_time), rel(rec.first_correct), rel(first_deliver), len(rec.deliver_times),
                rel(rec.handover),
                rec.first_correct is not None and (first_deliver is None or rec.first_correct <= first_deliver),
                rec.overtime, rec.point, rec.gui_status, rec.gui_source,
            ])

    def close(self):
        if self.round is not None:
            self.last_round, self.round = self.round, None
        self._finish_round()

    # ---------------- display text ----------------
    def _note(self, text):
        print(f"[EVAL] {text}")
        self.notes = (self.notes + [text])[-4:]

    def timer_text(self, now=None):
        now = self.clock() if now is None else now
        rec = self.round
        if self.mode == "test":
            if self.finished:
                return "TEST FINISHED"
            if rec is None:
                return "TEST"
            return f"TEST  row {rec.number} / {len(self.table)}   {now - rec.start:.0f} s"
        if self.phase == "RETRIEVAL" and self.phase_deadline:
            return f"RETRIEVAL  {max(0, self.phase_deadline - now):.0f} s"
        if self.phase in ("ASSEMBLY", "DELIVERY") and rec and rec.deadline:
            left = rec.deadline - now
            text = f"ASSEMBLY  {left:.0f} s" if left > 0 else f"OVERTIME  +{-left:.0f} s"
            if self.phase == "DELIVERY" and self.phase_deadline:
                text += f"   DELIVERY {max(0, self.phase_deadline - now):.0f} s"
            return text
        return {"IDLE": "WAITING FOR GUI", "PLAY": "RADIO GAME (to checkpoint)", "DONE": "CONDITION DONE"}.get(
            self.phase, self.phase)

    def status_lines(self, now=None):
        """[(text, BGR color)] for the panel above the table."""
        now = self.clock() if now is None else now
        rec = self.round
        head = (f"TEST  {self.answer_file}" if self.mode == "test" else
                f"{subject_tag(self.subject) if self.subject else 's??'}  {self.condition or '?'}"
                f"{'  [TRAINING]' if self.training else ''}   {self.answer_file or 'no answer file'}")
        timer = self.timer_text(now)
        timer_color = (60, 60, 60)
        if "OVERTIME" in timer:
            timer_color = (0, 0, 210)
        elif rec and rec.deadline and 0 < rec.deadline - now <= WARNING_SECONDS:
            timer_color = (0, 110, 230)
        lines = [(head, (40, 40, 40)), (timer, timer_color)]

        if rec and rec.active and not rec.armed:
            lines.append(("EVALUATION ACTIVE - clear the station / place the tray", (0, 150, 0)))
        elif rec and rec.active:
            lines.append((f"EVALUATION ACTIVE - prediction: {rec.prediction.upper()}", (0, 150, 0)))
        elif rec and rec.verdict:
            nxt = "  - say DELIVER for the next row" if self.mode == "test" else ""
            lines.append((f"Evaluated: {rec.verdict.upper()} ({rec.trigger.replace('_', ' ')}){nxt}", (0, 0, 0)))
        else:
            lines.append(("Evaluation inactive", (0, 0, 0)))

        if self.hand:
            cam = "station: hand at the station (holding last reading)"
        elif not self.tray:
            cam = "station: no tray on the station"
        else:
            cam = f"station: {fmt_slots(self.live_slots)}  (sum {slot_sum(self.live_slots or EMPTY)})"
        if self.camera_detail:
            cam += f"  - {self.camera_detail}"
        lines.append((cam, (0, 0, 200) if "NOT FOUND" in self.camera_detail else (90, 90, 90)))
        return lines


# ---------------------------------------------------------------------------
# Drawing (OpenCV): answer table next to the camera image
# ---------------------------------------------------------------------------
COLOR_BGR = {"Blue": (216, 78, 29), "Red": (30, 30, 200), "Yellow": (0, 97, 138), "Green": (61, 128, 21)}
MARK_ACTIVE = (0, 170, 0)     # evaluation running
MARK_IDLE = (0, 0, 0)         # evaluated / not active


def draw_mark(img, x, y, ok, color):
    import cv2
    if ok is None:
        return
    if ok:
        cv2.line(img, (x - 6, y), (x - 2, y + 5), color, 2, cv2.LINE_AA)
        cv2.line(img, (x - 2, y + 5), (x + 7, y - 7), color, 2, cv2.LINE_AA)
    else:
        cv2.line(img, (x - 5, y - 5), (x + 5, y + 5), color, 2, cv2.LINE_AA)
        cv2.line(img, (x - 5, y + 5), (x + 5, y - 5), color, 2, cv2.LINE_AA)


def render_panel(tracker, width=700, height=640, now=None):
    import cv2
    import numpy as np
    img = np.full((height, width, 3), 255, np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    def put(s, x, y, color=(0, 0, 0), scale=0.48, thick=1):
        cv2.putText(img, str(s), (int(x), int(y)), font, scale, color, thick, cv2.LINE_AA)

    y = 26
    for i, (line, color) in enumerate(tracker.status_lines(now)):
        put(line, 12, y, color, 0.62 if i < 3 else 0.5, 2 if i < 3 else 1)
        y += 26

    # table: # | Sum | Instruction | Answer (3 slots + marks) | Result
    x0, rh = 10, 25
    widths = [30, 40, 190, 336, width - 20 - 30 - 40 - 190 - 336]
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    top = y - 6
    cv2.rectangle(img, (x0, top), (xs[-1], top + rh), (79, 79, 47), -1)
    for i, h in enumerate(["#", "Sum", "Instruction", "Answer (slot 1 | 2 | 3)", "Result"]):
        put(h, xs[i] + 5, top + 17, (255, 255, 255), 0.47, 1)

    rec = tracker.round
    current = rec.row if rec is not None else None
    n_rows = 0
    for i, row in enumerate(tracker.table):
        ry = top + rh * (i + 1)
        if ry + rh > height - 4:
            break
        n_rows += 1
        is_current = i == current
        active = is_current and rec.active
        if is_current:
            bg = (214, 245, 214) if active else (228, 228, 228)
        elif not row.get("used", True):
            bg = (246, 246, 246)
        elif tracker.mode == "live":
            bg = (255, 237, 227)
        else:
            bg = (255, 255, 255) if i % 2 == 0 else (250, 249, 247)
        cv2.rectangle(img, (x0, ry), (xs[-1], ry + rh), bg, -1)
        text_color = (0, 0, 0) if row.get("used", True) else (160, 160, 160)
        put(row["piece"], xs[0] + 6, ry + 17, text_color)
        put(row["sum"], xs[1] + 6, ry + 17, text_color)
        put(row["instruction"], xs[2] + 5, ry + 17, text_color, 0.45)
        mark_color = MARK_ACTIVE if active else MARK_IDLE
        for k, color_name in enumerate(row["answer"]):
            cx = xs[3] + 6 + k * 110
            put(color_name, cx, ry + 17, COLOR_BGR.get(color_name, text_color), 0.48, 2)
            tw = cv2.getTextSize(color_name, font, 0.48, 2)[0][0]
            draw_mark(img, cx + tw + 14, ry + 12, row["marks"][k], mark_color)
        if row["result"]:
            put("OK" if row["result"] == "correct" else "MISTAKE", xs[4] + 5, ry + 17, (0, 0, 0), 0.47, 2)
        cv2.line(img, (x0, ry + rh), (xs[-1], ry + rh), (225, 213, 203), 1)
    for x in xs:
        cv2.line(img, (x, top), (x, top + rh * (n_rows + 1)), (225, 213, 203), 1)
    if current is not None and current < n_rows:
        ry = top + rh * (current + 1)
        cv2.rectangle(img, (x0, ry), (xs[-1], ry + rh), MARK_ACTIVE if rec.active else (0, 0, 0), 2)
    return img


def compose(camera_img, tracker, link_text=None, link_ok=True, now=None):
    """Camera image (left, 1024x576) + notes below it + answer table (right)."""
    import cv2
    import numpy as np
    h, cam_w, panel_w = 640, 1024, 700
    canvas = np.full((h, cam_w + panel_w, 3), 30, np.uint8)
    if camera_img is not None:
        canvas[:576, :cam_w] = cv2.resize(camera_img, (cam_w, 576))
    y = 596
    for note in tracker.notes[-2:]:
        cv2.putText(canvas, note[:120], (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
        y += 20
    if link_text:
        cv2.putText(canvas, link_text[:110], (12, 632), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 200, 0) if link_ok else (0, 0, 255), 1 if len(link_text) > 40 else 2, cv2.LINE_AA)
    canvas[:, cam_w:] = render_panel(tracker, panel_w, h, now)
    return canvas


# ---------------------------------------------------------------------------
# Camera + YOLO
# ---------------------------------------------------------------------------
class WebcamCaptureThread(threading.Thread):
    """Same interface as live_test.XimeaCaptureThread, for testing with a normal webcam."""

    def __init__(self, index=0):
        super().__init__(daemon=True)
        self.index = index
        self.frame_queue = queue.Queue(maxsize=2)
        self.running = True

    def run(self):
        import cv2
        cap = cv2.VideoCapture(self.index)
        while self.running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
            self.frame_queue.put(frame)
        cap.release()

    def stop(self):
        self.running = False


class StationReader:
    """Turns YOLO detections into the reading of the tray ON the station.

    detections: [(label, confidence, (x1, y1, x2, y2))] in image pixels.
    Returns dict(slots, hand, tray_on_station, tray_elsewhere, station, station_live, tray).
    """

    def __init__(self, station_label=STATION_LABEL, margin=STATION_MARGIN):
        self.station_label = station_label.lower()
        self.margin = margin
        self.station = None          # last station box (the station does not move)

    def _area(self):
        x1, y1, x2, y2 = self.station
        mx, my = (x2 - x1) * self.margin, (y2 - y1) * self.margin
        return x1 - mx, y1 - my, x2 + mx, y2 + my

    def _on_station(self, box):
        if self.station is None:
            return True                      # no station known: whole image (old behaviour)
        ax1, ay1, ax2, ay2 = self._area()
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        return ax1 <= cx <= ax2 and ay1 <= cy <= ay2

    def _touches_station(self, box):
        if self.station is None:
            return True
        ax1, ay1, ax2, ay2 = self._area()
        return box[0] < ax2 and box[2] > ax1 and box[1] < ay2 and box[3] > ay1

    def read(self, detections):
        dets = [(str(label).strip().lower(), float(conf), tuple(map(float, box))) for label, conf, box in detections]
        stations = [d for d in dets if d[0] == self.station_label]
        if stations:
            self.station = max(stations, key=lambda d: d[1])[2]
        out = {"slots": EMPTY, "hand": False, "tray_on_station": False, "tray_elsewhere": False,
               "station": self.station, "station_live": bool(stations), "tray": None}

        out["hand"] = any(d[0] == "hand" and self._touches_station(d[2]) for d in dets)
        trays = [d for d in dets if d[0] == "tray"]
        on = [d for d in trays if self._on_station(d[2])]
        out["tray_elsewhere"] = len(on) < len(trays)
        if not on:
            return out
        tray = max(on, key=lambda d: d[1])[2]
        out["tray_on_station"], out["tray"] = True, tray

        tx1, ty1, tx2, ty2 = tray
        width = (tx2 - tx1) / 3.0 or 1.0
        best = [None, None, None]            # (confidence, color) per slot, same zones as live_test.py
        for label, conf, (x1, y1, x2, y2) in dets:
            color = label.capitalize()
            if color not in COLOR_VALUES:
                continue
            bx, by = (x1 + x2) / 2, (y1 + y2) / 2
            if not (tx1 <= bx <= tx2 and ty1 <= by <= ty2):
                continue                     # battery not in the tray on the station: ignored
            k = max(0, min(2, int((bx - tx1) // width)))
            if best[k] is None or conf > best[k][0]:
                best[k] = (conf, color)
        out["slots"] = tuple(b[1] if b else None for b in best)
        return out


def camera_detail(reading):
    if reading["station"] is None:
        return "STATION NOT FOUND (whole image used)"
    if not reading["tray_on_station"] and reading["tray_elsewhere"]:
        return "tray off the station"
    return "" if reading["station_live"] else "station hidden (last position)"


def draw_station(img, reading):
    """Evaluation area on the camera image: green with a tray on it, grey without."""
    import cv2
    if reading["station"] is None:
        return img
    x1, y1, x2, y2 = (int(v) for v in reading["station"])
    color = (0, 200, 0) if reading["tray_on_station"] else (170, 170, 170)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 4)
    cv2.putText(img, "EVALUATION AREA", (x1, min(img.shape[0] - 8, y2 + 30)), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, color, 2, cv2.LINE_AA)
    return img


class CameraModel:
    def __init__(self, webcam=None):
        import torch
        from ultralytics import YOLO
        from live_test import CONFIDENCE, FPS_XIMEA, MC050_PRESET, MODEL_PATH, XimeaCaptureThread
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Model not found at: {MODEL_PATH}")
        self.device = 0 if torch.cuda.is_available() else "cpu"
        self.model = YOLO(MODEL_PATH)
        self.conf = CONFIDENCE
        self.station = StationReader()
        print(f"[INFO] YOLO on {self.device}, classes {self.model.names}")
        if not any(str(n).lower() == STATION_LABEL for n in self.model.names.values()):
            print(f"[WARN] The model has no '{STATION_LABEL}' class - the whole image is used.")
        self.cam = XimeaCaptureThread(MC050_PRESET, fps=FPS_XIMEA) if webcam is None else WebcamCaptureThread(webcam)
        self.cam.start()

    def read(self):
        """(annotated image, station reading dict) or None if no new frame."""
        try:
            frame = self.cam.frame_queue.get(timeout=0.2)
        except queue.Empty:
            return None
        results = self.model.predict(source=frame, conf=self.conf, device=self.device, verbose=False)[0]
        detections = [(self.model.names[int(b.cls[0].item())], b.conf[0].item(), b.xyxy[0].tolist())
                      for b in results.boxes]
        reading = self.station.read(detections)
        return draw_station(results.plot(), reading), reading

    def stop(self):
        self.cam.stop()


# ---------------------------------------------------------------------------
# LSL plumbing (live mode)
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


def drain(q, tracker):
    while True:
        try:
            marker, ts = q.get_nowait()
        except queue.Empty:
            return
        tracker.handle_marker(marker, ts)


# ---------------------------------------------------------------------------
# Test-mode helpers
# ---------------------------------------------------------------------------
def choose_log_file(arg):
    log_dir = os.path.join(base_dir, "log_files")
    if arg and arg != "pick":
        for cand in (arg, os.path.join(log_dir, arg), os.path.join(log_dir, arg + ".txt")):
            if os.path.isfile(cand):
                return cand
        raise SystemExit(f"Log file not found: {arg}")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title="Choose the log file to test", initialdir=log_dir,
                                          filetypes=[("Log files", "*.txt"), ("All files", "*.*")])
        root.destroy()
        if path:
            return path
        raise SystemExit("No file chosen.")
    except Exception as e:      # no tkinter / no display: type the name instead
        print(f"[INFO] No file window ({e}).")
    files = sorted(f for f in os.listdir(log_dir) if f.endswith(".txt"))
    print("Log files:", ", ".join(os.path.splitext(f)[0] for f in files))
    name = input("File to test (e.g. s03_audio): ").strip()
    return choose_log_file(name)


class VoiceState:
    def __init__(self):
        self.listener = None
        self.status = "voice OFF"
        self.heard = ""

    @property
    def on(self):
        return self.listener is not None and self.listener.stream is not None


def start_voice(on_deliver, mic=None):
    """Vosk 'deliver' listener from voice.py (same words as the GUI). Always returns a VoiceState;
    its .status says why voice is off (missing package, model, microphone...)."""
    state = VoiceState()
    try:
        from voice import VoiceDeliverListener
        listener = VoiceDeliverListener(input_keyword=mic) if mic else VoiceDeliverListener()
    except ImportError as e:
        state.status = f"voice OFF: {e} (pip install vosk sounddevice PyQt5)"
        print(f"[VOICE] {state.status} - press D for deliver.")
        return state
    except Exception as e:
        state.status = f"voice OFF: {e}"
        print(f"[VOICE] {state.status} - press D for deliver.")
        return state
    if not listener.vosk_ready:
        state.status = f"voice OFF: {listener.status}"
        print(f"[VOICE] {state.status} - press D for deliver.")
        return state
    last = [0.0]

    def emit():   # replaces the Qt signal: no Qt event loop in this script
        now = time.monotonic()
        if now - last[0] >= VOICE_COOLDOWN_SECONDS:
            last[0] = now
            on_deliver()
    def heard(text, final):
        state.heard = text

    listener._emit_deliver = emit
    listener.on_text = heard
    listener.set_enabled(True)
    state.listener = listener
    state.status = ("voice ON: " if listener.stream is not None else "voice OFF: ") + listener.status
    print(f"[VOICE] {state.status}")
    if listener.stream is not None:
        print("[VOICE] Say 'deliver' (or press D).")
    return state


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------
def run_test(args):
    import cv2
    path = choose_log_file(args.test)
    tracker = ParadigmTracker(time.monotonic, lambda msg: print(f"[TEST] {msg}"),
                              stable_frames=args.stable_frames, mode="test")
    tracker.start_test(path)
    camera = CameraModel(args.webcam)
    deliver_event = threading.Event()
    voice = start_voice(deliver_event.set, args.mic)
    cv2.namedWindow("Battery evaluator - TEST", cv2.WINDOW_NORMAL)
    image = None
    try:
        while True:
            got = camera.read()
            if got is not None:
                image, reading = got
                tracker.update_reading(reading["slots"], reading["hand"], reading["tray_on_station"],
                                       detail=camera_detail(reading))
            if deliver_event.is_set():
                deliver_event.clear()
                tracker.deliver()
            text = voice.status + (f'   heard: "{voice.heard}"' if voice.heard else "") + "   (D = deliver)"
            cv2.imshow("Battery evaluator - TEST", compose(image, tracker, text, voice.on))
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("d"), ord("D")):
                tracker.deliver()
            elif key in (ord("r"), ord("R")):
                tracker.redo_row()
    finally:
        if voice.listener is not None:
            voice.listener.stop()
        camera.stop()
        tracker.close()
        cv2.destroyAllWindows()
        if tracker.csv_path:
            print(f"[INFO] Log: {tracker.csv_path}")


def run_live(args):
    import pylsl
    send = make_outlet()
    tracker = ParadigmTracker(pylsl.local_clock, send, args.subject, args.condition, args.stable_frames)
    q = queue.Queue()
    listener = MarkerListener(q)
    listener.start()
    send("Eval_Started")
    try:
        if args.no_camera:
            print("[INFO] No camera: following the GUI only. Ctrl+C to stop.")
            last = None
            try:
                while True:
                    drain(q, tracker)
                    text = " | ".join(t for t, _ in tracker.status_lines()[:2])
                    text += "" if listener.connected else "  (GUI not found)"
                    if text != last:
                        print("[HUD]", text)
                        last = text
                    time.sleep(0.05)
            except KeyboardInterrupt:
                pass
        else:
            import cv2
            camera = CameraModel(args.webcam)
            cv2.namedWindow("Battery evaluator", cv2.WINDOW_NORMAL)
            image = None
            try:
                while True:
                    drain(q, tracker)
                    got = camera.read()
                    if got is not None:
                        image, reading = got
                        tracker.update_reading(reading["slots"], reading["hand"], reading["tray_on_station"],
                                               detail=camera_detail(reading))
                    link = "GUI linked" if listener.connected else "GUI NOT FOUND"
                    cv2.imshow("Battery evaluator", compose(image, tracker, link, listener.connected))
                    if (cv2.waitKey(1) & 0xFF) in (ord("q"), ord("Q"), 27):
                        break
            finally:
                camera.stop()
                cv2.destroyAllWindows()
    finally:
        listener.running = False
        tracker.close()
        send("Eval_Stopped")
        if tracker.csv_path:
            print(f"[INFO] Log: {tracker.csv_path}")


def main():
    global SEND_VERDICTS, TRAY_GONE_SECONDS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", nargs="?", const="pick", metavar="FILE",
                    help="test mode without the GUI; FILE like s03_audio (no FILE = choose in a window)")
    ap.add_argument("--webcam", type=int, default=None, metavar="N", help="use webcam N instead of the XIMEA")
    ap.add_argument("--mic", metavar="NAME", help="test mode: part of the microphone name (e.g. Bose); "
                                                  "default = config.VOICE_INPUT_KEYWORD / Windows default")
    ap.add_argument("--subject", help="live mode: subject number, if started after the GUI setup screen")
    ap.add_argument("--condition", help="live mode: GUI condition name (baseline, audio, haptic, ...)")
    ap.add_argument("--no-camera", action="store_true", help="live mode: only follow the GUI markers")
    ap.add_argument("--stable-frames", type=int, default=STABLE_FRAMES)
    ap.add_argument("--tray-gone", type=float, default=TRAY_GONE_SECONDS,
                    help="seconds the tray must be off the station before it is evaluated")
    ap.add_argument("--predict-only", action="store_true", help="live mode: never send verdicts to the GUI")
    args = ap.parse_args()
    SEND_VERDICTS = SEND_VERDICTS and not args.predict_only
    TRAY_GONE_SECONDS = args.tray_gone
    if args.test:
        run_test(args)
    else:
        run_live(args)


if __name__ == "__main__":
    main()
