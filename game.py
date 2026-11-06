"""Plant-radio game: a radio talks continuously; when something breaks it says which buttons to press.

Bimodal by design:
  * WHAT to press exists only in the audio (no captions anywhere on screen).
  * WHERE it is exists only on the screen: 3 buttons (Left / Up / Right keys) whose colors and
    words keep changing and never match each other (Stroop). They freeze while a problem is active.

Hard mode (state.game_mode == "hard"): while no instruction is active, every button change is a
"match round": exactly one button's word matches its color; pressing it scores IDLE_HIT_POINTS,
a miss costs nothing, one press per round. Instructions pay double and cost double.

Public API used by DualTaskScreen:
    start(), stop(), shutdown(), press(pos), set_pause(...), set_pause_seconds(n),
    set_system_failed(active, blink), set_counting(on), reset_checkpoint_counter(),
    announce(key) and the `score` attribute; emits `checkpoint_reached`.
"""

import csv
import os
import random
import time
from collections import deque

from PyQt5.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from audio import audio_sys
from config import (
    FAIL_PENALTY, FILLER_GAP_SECONDS, HARD_INSTRUCTION_MULTIPLIER, HARD_PENALTY_MULTIPLIER,
    IDLE_HIT_POINTS, IDLE_WRONG_PENALTY, LATE_PRESS_SECONDS, ROULETTE_DURING_INSTRUCTION, ROULETTE_FRAME_SECONDS, LOG_TRAINING_CSV, POINTS_PER_STEP,
    PRESS_GRACE_SECONDS, PROBLEM_GAP_SECONDS, PROBLEMS_PER_CHECKPOINT, RESPONSE_SECONDS,
    RESUME_GAP_SECONDS, SHOW_RESPONSE_BAR, SHUFFLE_SECONDS, base_dir
)
from lsl_markers import send_marker
from panel_logic import (
    build_pool, layout_for, layout_to_str, match_layout, problem_order, random_layout, resolve_targets,
    steps_to_str
)
from radio import ClipBank, RadioPlayer
from radio_script import FEEDBACK, FILLER, LABELS, all_clips
from state import state
from texts import t

COLOR_HEX = {"red": "#E53935", "blue": "#1E5BD8", "green": "#1E9E4A", "yellow": "#F5C518", "purple": "#8E44C9"}
KEY_GLYPHS = ["←", "↑", "→"]
CHARS_PER_SECOND = 14.0          # duration estimate when a clip is missing (silent mode)

_POOL = None


def _pool():
    global _POOL
    if _POOL is None:
        _POOL = build_pool()
    return _POOL


class RadioPanelGame(QWidget):
    checkpoint_reached = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(560)
        self.setFocusPolicy(Qt.StrongFocus)

        self.player = None
        self.bank = None
        self.clip_texts = {}
        self.running = False

        self.score = 0
        self.paused = False
        self.pause_title = ""
        self.pause_subtitle = ""
        self.pause_seconds_left = 0
        self.system_failed_active = False
        self.system_failed_blink = False

        self.counting = True
        self.counted = 0
        self.pending_checkpoint = False

        self.rng = random.Random(0)
        self.layout = random_layout(self.rng)
        self.problem = None
        self.order = []
        self.order_idx = 0
        self.recent_fillers = deque(maxlen=6)
        self.next_problem_at = self.next_filler_at = self.next_shuffle_at = 0.0
        self.flash = None                 # (outcome, time)
        self.hard = False
        self.roulette = False
        self.idle = None                  # current match round (hard mode)
        self.prev_idle = None             # last closed round, can still take a late press
        self.idle_n = 0
        self.popups = []                  # (pos, text, color, time)
        self._paused_at = 0.0
        self.key_flash = [0.0, 0.0, 0.0]
        self.eq = [0.0] * 18
        self.csv_path = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ public API
    def start(self):
        lang = state.language
        cond = state.current_condition
        if self.player is None:
            self.player = RadioPlayer(device=audio_sys.participant_device)
        blocks, training = _pool()
        problems = [p for b in blocks for p in b] + training
        self.clip_texts = all_clips(lang, problems)
        if self.bank is None or self.bank.lang != lang:
            self.bank = ClipBank(lang, self.player.sr)
            self.bank.check(list(self.clip_texts))
        for msg in self.bank.problems[:3]:
            print(f"RADIO WARNING: {msg}")

        self.order = problem_order(cond, blocks, training)
        self.order_idx = 0
        self.rng = random.Random(f"radio-{cond}")
        self.score = 0
        self.problem = None
        self.paused = False
        self.system_failed_active = False
        self.counting = True
        self.counted = 0
        self.pending_checkpoint = False
        self.flash = None
        self.csv_path = None
        self.hard = state.game_mode == "hard"
        self.roulette = state.game_mode in ROULETTE_DURING_INSTRUCTION
        self.idle = self.prev_idle = None
        self.idle_n = 0
        self.popups = []

        now = time.perf_counter()
        self._new_layout(now)
        self.next_filler_at = now + 0.5
        self.next_problem_at = now + 6.0
        self.next_shuffle_at = now + SHUFFLE_SECONDS
        self.running = True
        self.player.stop()
        send_marker(f"Radio_Game_Start_Mode_{state.game_mode}_Lang_{lang}_Voice_{(self.bank.voice or 'none').replace(' ', '')}"
                    f"_Silent_{int(self.player.silent or not self.bank.ok)}")
        self.timer.start(30)
        self.update()

    def stop(self):
        if self.problem is not None:
            self._interrupt("stopped")
        self._close_idle(time.perf_counter(), "stopped")
        self._finalize_prev_idle(force=True)
        self.running = False
        self.timer.stop()
        if self.player is not None:
            self.player.stop()
        self.update()

    def shutdown(self):
        self.stop()
        if self.player is not None:
            self.player.close()

    def set_pause(self, paused, title="", subtitle="", seconds_left=0):
        self.pause_title, self.pause_subtitle, self.pause_seconds_left = title, subtitle, seconds_left
        now = time.perf_counter()
        if paused and not self.paused:
            self._paused_at = now
            self._close_idle(now, "paused")
            self._finalize_prev_idle(force=True)
            if self.problem is not None:
                self._hold_problem(now)
            if self.player is not None:
                self.player.stop()
        elif not paused and self.paused:
            if self.problem is not None:
                self._resume_problem(now)
            self.next_problem_at = max(self.next_problem_at, now + RESUME_GAP_SECONDS)
            self.next_filler_at = now + 0.4
            if self.problem is None:
                self.next_shuffle_at = now          # fresh match round right away
        self.paused = paused
        self.update()

    def set_pause_seconds(self, n):
        self.pause_seconds_left = n
        self.update()

    def set_system_failed(self, active, blink_state=True):
        self.system_failed_active = active
        self.system_failed_blink = blink_state
        self.update()

    def set_counting(self, on):
        self.counting = on

    def reset_checkpoint_counter(self):
        self.counted = 0
        self.pending_checkpoint = False

    def announce(self, key):
        """Play an announcement clip (e.g. 'container_1') in the chosen language. False if missing."""
        cid = f"ann_{key}"
        if self.player is None or self.bank is None or not self.bank.has(cid):
            return False
        self.player.play(cid, self.bank.clips[cid], self.bank.durations[cid])
        return True

    def press(self, pos):
        """pos 0 = Left key, 1 = Up key (middle), 2 = Right key."""
        if not self.running or self.paused:
            return
        now = time.perf_counter()
        self.key_flash[pos] = now
        p = self.problem
        if p is None:
            if self.hard:
                if not self._late_idle_press(pos, now):
                    if self.idle is not None:
                        self._idle_answer(self.idle, pos, now)
                    else:
                        send_marker(f"Radio_Press_NoTarget_Pos_{pos}")
            else:
                send_marker(f"Radio_Press_NoProblem_Pos_{pos}")
            self.update()
            return
        if self._spinning():
            # Buttons are spinning while the radio speaks: arrows are locked
            # (a press right at the start may still belong to the match round that was just replaced)
            if not (self.hard and self._late_idle_press(pos, now)):
                send_marker(f"Radio_Press_Blocked_{p['id']}_Pos_{pos}")
            self.update()
            return
        if now - p["onset"] < PRESS_GRACE_SECONDS:
            if not (self.hard and self._late_idle_press(pos, now)):
                send_marker(f"Radio_Press_Ignored_Grace_{p['id']}_Pos_{pos}")
            self.update()
            return
        p["presses"].append(pos)
        if pos == p["targets"][p["progress"]]:
            p["progress"] += 1
            send_marker(f"Radio_Press_Correct_{p['id']}_Step_{p['progress']}_Pos_{pos}")
            if p["progress"] == len(p["targets"]):
                self._resolve("solved", now)
        else:
            send_marker(f"Radio_Press_Wrong_{p['id']}_Step_{p['progress'] + 1}_Pos_{pos}"
                        f"_Expected_{p['targets'][p['progress']]}")
            self._resolve("wrong", now)
        self.update()

    # ------------------------------------------------------------------ engine
    def _duration(self, cid):
        if self.bank is not None and self.bank.has(cid):
            return self.bank.durations[cid]
        parts = self.clip_texts.get(cid, [""])
        return max(1.0, len(" ".join(parts)) / CHARS_PER_SECOND)

    def _play(self, cid):
        samples = self.bank.clips.get(cid) if self.bank is not None else None
        self.player.play(cid, samples, self._duration(cid))

    def _tick(self):
        now = time.perf_counter()
        finished = self.player.poll_finished()
        if finished:
            self._on_clip_finished(finished, now)
        self._animate_eq()
        if self.paused or not self.running:
            self.update()
            return

        p = self.problem
        if p is not None and p["deadline"] is not None and now > p["deadline"]:
            send_marker(f"Radio_Press_Timeout_{p['id']}_Step_{p['progress'] + 1}")
            self._resolve("timeout", now)

        if not self.player.busy():
            if self.pending_checkpoint and self.problem is None:
                self.pending_checkpoint = False
                send_marker("Radio_Checkpoint_Due")
                self.checkpoint_reached.emit()
                return
            if self.problem is None and now >= self.next_problem_at:
                self._start_problem(now)
            elif self.problem is None and now >= self.next_filler_at:
                self._play_filler()

        if self.problem is None and now >= self.next_shuffle_at:
            self._new_layout(now)
        self._finalize_prev_idle()
        self.update()

    def _on_clip_finished(self, cid, now):
        p = self.problem
        if p is not None and cid == p["clip"]:
            p["instr_end"] = now
            p["deadline"] = now + RESPONSE_SECONDS
            send_marker(f"Radio_Instruction_End_{p['id']}")
        self.next_filler_at = now + self.rng.uniform(*FILLER_GAP_SECONDS)

    def _play_filler(self):
        n = len(FILLER["en"])
        choices = [i for i in range(n) if i not in self.recent_fillers] or list(range(n))
        i = self.rng.choice(choices)
        self.recent_fillers.append(i)
        self._play(f"filler_{i:02d}")

    def _start_problem(self, now):
        if self.order_idx and self.order_idx % len(self.order) == 0:
            send_marker(f"Radio_Problem_Set_Exhausted_Reusing_Cycle_{self.order_idx // len(self.order) + 1}")
        base = self.order[self.order_idx % len(self.order)]
        self.order_idx += 1
        self._close_idle(now, "instruction")
        layout = layout_for(base["steps"], self.rng)
        targets = resolve_targets(layout, base["steps"])
        self.layout = layout
        clip = f"prob_{base['id']}"
        self.problem = {
            "id": base["id"], "type": base["type"], "steps": base["steps"], "layout": layout,
            "targets": targets, "progress": 0, "presses": [], "clip": clip,
            "onset": now, "instr_dur": self._duration(clip), "instr_end": None, "deadline": None,
            "counted": self.counting, "paused_s": 0.0, "paused_after_instr": 0.0, "replays": 0,
        }
        self._play(clip)
        send_marker(f"Radio_Problem_Start_{base['id']}_Type_{base['type']}_Steps_{steps_to_str(base['steps'])}"
                    f"_Layout_{layout_to_str(layout)}_Targets_{'-'.join(map(str, targets))}"
                    f"_Counted_{int(self.counting)}")

    def _resolve(self, outcome, now):
        p = self.problem
        self.problem = None
        rt = now - p["onset"] - p["paused_s"]
        if p["instr_end"] is not None:
            end = p["instr_end"]
        else:                                  # answered while the radio was still talking
            end = p.get("replay_start", p["onset"]) + p["instr_dur"]
        rt_after = now - end - p["paused_after_instr"]   # negative = answered before the instruction ended
        if outcome == "solved":
            mult = HARD_INSTRUCTION_MULTIPLIER if self.hard else 1
            self.score += POINTS_PER_STEP * len(p["targets"]) * mult
        else:
            mult = HARD_PENALTY_MULTIPLIER if self.hard else 1
            self.score = max(0, self.score - FAIL_PENALTY * mult)
        send_marker(f"Radio_Problem_{outcome.capitalize()}_{p['id']}_RT_{rt:.3f}"
                    f"_RTafterInstr_{rt_after:.3f}_Score_{self.score}")

        self.player.stop()
        fb = f"fb_{outcome}_{self.rng.randrange(len(FEEDBACK['en'][outcome]))}"
        self._play(fb)
        fb_dur = self._duration(fb)
        self.flash = (outcome, now)

        if p["counted"] and self.counting:
            self.counted += 1
            if self.counted >= PROBLEMS_PER_CHECKPOINT:
                self.counted = 0
                self.pending_checkpoint = True
        self.next_problem_at = now + fb_dur + self.rng.uniform(*PROBLEM_GAP_SECONDS)
        self.next_shuffle_at = now              # hard mode: next match round right away
        self._log(p, outcome, rt, rt_after)

    def _spinning(self):
        """True while the radio is still giving the instruction and the buttons are hidden."""
        p = self.problem
        return self.roulette and p is not None and p["instr_end"] is None and not self.paused

    # ------------------------------------------------------------------ hard mode: match rounds
    def _new_layout(self, now):
        """Idle button change. Normal mode: all mismatched. Hard mode: a new match round."""
        self._close_idle(now, "changed")
        if self.hard:
            self.layout, target = match_layout(self.rng)
            self.idle_n += 1
            self.idle = {"n": self.idle_n, "layout": self.layout, "target": target, "shown_at": now,
                         "answered": False, "presses": []}
            send_marker(f"Radio_Match_Round_{self.idle_n}_Target_{target}_Layout_{layout_to_str(self.layout)}")
        else:
            self.layout = random_layout(self.rng)
        self.next_shuffle_at = now + SHUFFLE_SECONDS

    def _close_idle(self, now, why):
        """End the current match round; it can still take a press for LATE_PRESS_SECONDS."""
        if self.idle is None:
            return
        self._finalize_prev_idle(force=True)
        self.idle["closed_at"] = now
        self.idle["closed_by"] = why
        self.prev_idle, self.idle = self.idle, None

    def _late_idle_press(self, pos, now):
        pi = self.prev_idle
        if pi is not None and not pi["answered"] and now - pi["closed_at"] <= LATE_PRESS_SECONDS:
            self._idle_answer(pi, pos, now, late=True)
            return True
        return False

    def _finalize_prev_idle(self, force=False):
        pi = self.prev_idle
        if pi is None:
            return
        if not force and time.perf_counter() - pi["closed_at"] <= LATE_PRESS_SECONDS:
            return
        self.prev_idle = None
        if not pi["answered"] and pi["closed_by"] not in ("paused", "stopped"):
            send_marker(f"Radio_Match_Miss_{pi['n']}")
            self._log_idle(pi, "miss", None)

    def _idle_answer(self, idle, pos, now, late=False):
        idle["presses"].append(pos)
        if idle["answered"]:
            send_marker(f"Radio_Match_Extra_Press_{idle['n']}_Pos_{pos}")
            return
        idle["answered"] = True
        rt = now - idle["shown_at"]
        if pos == idle["target"]:
            self.score += IDLE_HIT_POINTS
            outcome = "hit"
            self.popups.append((pos, f"+{IDLE_HIT_POINTS}", "#4ADE80", now))
        else:
            self.score = max(0, self.score - IDLE_WRONG_PENALTY)
            outcome = "wrong"
            self.popups.append((pos, "✗" if not IDLE_WRONG_PENALTY else f"-{IDLE_WRONG_PENALTY}", "#F87171", now))
        send_marker(f"Radio_Match_{outcome.capitalize()}_{idle['n']}_Pos_{pos}_Target_{idle['target']}"
                    f"_RT_{rt:.3f}_Late_{int(late)}_Score_{self.score}")
        self._log_idle(idle, outcome, rt)

    def _hold_problem(self, now):
        """A pause (e.g. saying DELIVER) freezes the active problem instead of cancelling it,
        so a pause can never be used to escape a hard instruction."""
        p = self.problem
        if p["instr_end"] is None:
            p["replay"] = True                       # instruction was cut: say it again afterwards
        else:
            p["remaining"] = max(1.0, p["deadline"] - now)
            p["deadline"] = None
        send_marker(f"Radio_Problem_Held_{p['id']}_Replay_{int(p.get('replay', False))}")

    def _resume_problem(self, now):
        p = self.problem
        p["paused_s"] += now - self._paused_at
        if p.pop("replay", False):
            p["replays"] += 1
            p["replay_start"] = now
            self._play(p["clip"])                    # deadline starts when the replay ends
        else:
            p["paused_after_instr"] += now - self._paused_at
            p["deadline"] = now + p.pop("remaining")
        send_marker(f"Radio_Problem_Resumed_{p['id']}")

    def _interrupt(self, why):
        p = self.problem
        self.problem = None
        send_marker(f"Radio_Problem_Interrupted_{p['id']}_{why}")
        self._log(p, f"interrupted_{why}", time.perf_counter() - p["onset"] - p["paused_s"], None)

    # ------------------------------------------------------------------ logging
    def _log(self, p, outcome, rt, rt_after):
        self._write_row([
            p["id"], p["type"], len(p["steps"]), steps_to_str(p["steps"]), layout_to_str(p["layout"]),
            "-".join(map(str, p["targets"])), "-".join(map(str, p["presses"])), int(p["counted"]),
            outcome, round(rt, 3), "" if rt_after is None else round(rt_after, 3),
            round(p["paused_s"], 3), p["replays"]])

    def _log_idle(self, idle, outcome, rt):
        self._write_row([
            f"match{idle['n']:04d}", "match", 1, "", layout_to_str(idle["layout"]), idle["target"],
            "-".join(map(str, idle["presses"])), 0, outcome, "" if rt is None else round(rt, 3), "", 0, 0])

    def _write_row(self, values):
        if state.training_active and not LOG_TRAINING_CSV:
            return
        try:
            if self.csv_path is None:
                log_dir = os.path.join(base_dir, "logs")
                os.makedirs(log_dir, exist_ok=True)
                try:
                    subj = f"s{int(state.subject_number):02d}"
                except ValueError:
                    subj = f"s_{state.subject_number}"
                stamp = time.strftime("%Y%m%d_%H%M%S")
                self.csv_path = os.path.join(log_dir, f"{subj}_{state.current_condition}_radio_{stamp}.csv")
                with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([
                        "subject", "condition", "game_mode", "language", "problem_id", "type", "n_steps", "steps",
                        "layout", "targets", "presses", "counted_for_checkpoint", "outcome",
                        "rt_from_onset_s", "rt_after_instruction_s", "paused_s", "instruction_replays",
                        "score"])
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    [state.subject_number, state.current_condition, state.game_mode, state.language]
                    + values + [self.score])
        except Exception as e:
            print(f"Radio log error: {e}")

    # ------------------------------------------------------------------ drawing
    def _animate_eq(self):
        talking = self.player is not None and self.player.busy() and not self.paused
        for i in range(len(self.eq)):
            target = self.rng.random() * (0.35 + 0.65 * (1 - abs(i - 8.5) / 9)) if talking else 0.04
            self.eq[i] += (target - self.eq[i]) * 0.45

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        now = time.perf_counter()
        lang = state.language

        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, QColor("#0B1220"))
        bg.setColorAt(1, QColor("#111A2E"))
        painter.fillRect(0, 0, w, h, QBrush(bg))

        # Outcome flash around the panel
        if self.flash is not None and now - self.flash[1] < 0.7:
            col = QColor("#22C55E") if self.flash[0] == "solved" else QColor("#EF4444")
            painter.setPen(QPen(col, 10))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(5, 5, w - 10, h - 10), 14, 14)

        # HUD
        hud = QRectF(12, 12, w - 24, 54)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 220))
        painter.drawRoundedRect(hud, 10, 10)
        painter.setFont(QFont("Helvetica", 18, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(hud.adjusted(14, 0, -14, 0), Qt.AlignLeft | Qt.AlignVCenter,
                         f"{t('score')}: {self.score:04d}")
        painter.setPen(QColor("#38BDF8"))
        right = t("next_cp", n=PROBLEMS_PER_CHECKPOINT - self.counted) if self.counting else t("assembly_mode")
        painter.drawText(hud.adjusted(14, 0, -14, 0), Qt.AlignRight | Qt.AlignVCenter, right)

        # Radio: title, on-air lamp, equalizer
        radio = QRectF(w * 0.12, 84, w * 0.76, h * 0.2)
        painter.setBrush(QColor("#0F172A"))
        painter.setPen(QPen(QColor("#334155"), 2))
        painter.drawRoundedRect(radio, 14, 14)
        painter.setFont(QFont("Helvetica", 15, QFont.Bold))
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(QRectF(radio.left() + 18, radio.top() + 8, radio.width() - 36, 28),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         t("radio_title") + (f"  ·  {t('mode_hard')}" if self.hard else ""))
        talking = self.player is not None and self.player.busy() and not self.paused
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#EF4444") if talking else QColor("#4B5563"))
        painter.drawEllipse(QPointF(radio.right() - 26, radio.top() + 22), 8, 8)
        bars = len(self.eq)
        area = QRectF(radio.left() + 22, radio.top() + 44, radio.width() - 44, radio.height() - 58)
        bw = area.width() / bars
        painter.setBrush(QColor("#38BDF8"))
        for i, v in enumerate(self.eq):
            bh = max(3.0, v * area.height())
            painter.drawRoundedRect(QRectF(area.left() + i * bw + bw * 0.2, area.bottom() - bh, bw * 0.6, bh), 2, 2)

        # Response time bar (only after the instruction has ended)
        p = self.problem
        # Hard mode: tell the participant which task is on
        bar_y = radio.bottom() + 18
        if self.hard and not self.paused:
            status = None
            if p is not None:
                status = (t("status_answer"), "#FB923C") if p["instr_end"] is not None \
                    else (t("status_wait"), "#FACC15")
            elif self.idle is not None:
                status = (t("status_match"), "#4ADE80")
            srect = QRectF(w * 0.12, radio.bottom() + 12, w * 0.76, 46)
            if status is not None:
                col = QColor(status[1])
                painter.setPen(QPen(col, 3))
                bgc = QColor(col)
                bgc.setAlpha(40)
                painter.setBrush(bgc)
                painter.drawRoundedRect(srect, 12, 12)
                size = 22
                font = QFont("Helvetica", size, QFont.Black)
                while size > 11 and QFontMetrics(font).horizontalAdvance(status[0]) > srect.width() - 24:
                    size -= 1
                    font.setPointSize(size)
                painter.setFont(font)
                painter.setPen(col)
                painter.drawText(srect, Qt.AlignCenter, status[0])
            bar_y = srect.bottom() + 12
        if SHOW_RESPONSE_BAR and p is not None and p["deadline"] is not None:
            frac = max(0.0, min(1.0, (p["deadline"] - now) / RESPONSE_SECONDS))
            full = QRectF(w * 0.12, bar_y, w * 0.76, 12)
            painter.setBrush(QColor("#1E293B"))
            painter.drawRoundedRect(full, 6, 6)
            painter.setBrush(QColor("#FACC15") if frac > 0.35 else QColor("#EF4444"))
            painter.drawRoundedRect(QRectF(full.left(), full.top(), full.width() * frac, 12), 6, 6)

        # Buttons
        top = bar_y + 40
        gap = w * 0.04
        bw = (w - 2 * w * 0.06 - 2 * gap) / 3
        bh = min(bw * 0.9, h - top - 110)
        spinning = self._spinning()
        faces = self.layout
        if spinning:   # random faces, real buttons hidden until the instruction ends
            frame = int(now / ROULETTE_FRAME_SECONDS)
            faces = random_layout(random.Random(frame))
        for pos, (fill, label) in enumerate(faces):
            x = w * 0.06 + pos * (bw + gap)
            rect = QRectF(x, top, bw, bh)
            painter.setPen(QPen(QColor("#E2E8F0"), 3))
            painter.setBrush(QColor(COLOR_HEX[fill]))
            painter.drawRoundedRect(rect, 18, 18)
            if now - self.key_flash[pos] < 0.15:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 90))
                painter.drawRoundedRect(rect, 18, 18)
            self._draw_label(painter, rect, LABELS.get(lang, LABELS["en"])[label])
            if p is not None and pos in p["targets"][:p["progress"]]:
                painter.setPen(QPen(QColor("#FFFFFF"), 6))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(5, 5, -5, -5), 14, 14)
                badge = QRectF(rect.right() - 46, rect.top() - 14, 52, 52)
                painter.setPen(QPen(QColor("#FFFFFF"), 3))
                painter.setBrush(QColor("#16A34A"))
                painter.drawEllipse(badge)
                painter.setFont(QFont("Helvetica", 22, QFont.Bold))
                painter.drawText(badge, Qt.AlignCenter, "✓")
            # key cap
            cap = QRectF(rect.center().x() - 34, rect.bottom() + 16, 68, 52)
            painter.setPen(QPen(QColor("#334155" if spinning else "#64748B"), 2))
            painter.setBrush(QColor("#0F172A" if spinning else "#1E293B"))
            painter.drawRoundedRect(cap, 10, 10)
            painter.setPen(QColor("#475569" if spinning else "#E2E8F0"))
            painter.setFont(QFont("Helvetica", 24, QFont.Bold))
            painter.drawText(cap, Qt.AlignCenter, KEY_GLYPHS[pos])
            if spinning:   # locked: dim veil + strike over the key cap
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(11, 18, 32, 70))
                painter.drawRoundedRect(rect, 18, 18)
                painter.setPen(QPen(QColor("#94A3B8"), 3))
                painter.drawLine(cap.topLeft() + QPointF(10, 10), cap.bottomRight() - QPointF(10, 10))

        # Match-round feedback (hard mode)
        self.popups = [pp for pp in self.popups if now - pp[3] < 0.9]
        for pos, text, color, t0 in self.popups:
            age = (now - t0) / 0.9
            x = w * 0.06 + pos * (bw + gap)
            c = QColor(color)
            c.setAlpha(int(255 * (1 - age)))
            painter.setPen(QPen(c, 6))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(x, top, bw, bh), 18, 18)
            painter.setPen(c)
            painter.setFont(QFont("Helvetica", 30, QFont.Black))
            painter.drawText(QRectF(x, top - 50 - 30 * age, bw, 44), Qt.AlignCenter, text)

        if self.bank is not None and (not self.bank.ok or (self.player and self.player.silent)):
            painter.setPen(QColor("#F97316"))
            painter.setFont(QFont("Helvetica", 12, QFont.Bold))
            painter.drawText(QRectF(0, h - 26, w, 22), Qt.AlignCenter, t("audio_missing"))

        if self.paused:
            self._draw_pause(painter, w, h)
        if self.system_failed_active:
            self._draw_failed(painter, w, h)

    def _draw_label(self, painter, rect, text):
        size = int(rect.height() * 0.24)
        font = QFont("Helvetica", size, QFont.Black)
        while size > 10 and QFontMetrics(font).horizontalAdvance(text) > rect.width() * 0.84:
            size -= 1
            font.setPointSize(size)
        fm = QFontMetrics(font)
        path = QPainterPath()
        x = rect.center().x() - fm.horizontalAdvance(text) / 2
        y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
        path.addText(QPointF(x, y), font, text)
        painter.setPen(QPen(QColor("#0B0F19"), max(3, size // 8), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawPath(path)

    def _draw_pause(self, painter, w, h):
        overlay = QRectF(25, h * 0.25, w - 50, h * 0.45)
        painter.setPen(QPen(QColor("#38BDF8"), 4))
        painter.setBrush(QColor(15, 23, 42, 240))
        painter.drawRoundedRect(overlay, 16, 16)
        painter.setPen(QColor("#38BDF8"))
        painter.setFont(QFont("Helvetica", 24, QFont.Bold))
        painter.drawText(QRectF(40, h * 0.28, w - 80, 50), Qt.AlignCenter, self.pause_title)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Helvetica", 20, QFont.Bold))
        painter.drawText(QRectF(40, h * 0.36, w - 80, 90), Qt.AlignCenter | Qt.TextWordWrap, self.pause_subtitle)
        painter.setPen(QColor("#FACC15"))
        painter.setFont(QFont("Helvetica", 48, QFont.Bold))
        painter.drawText(QRectF(40, h * 0.51, w - 80, 80), Qt.AlignCenter, f"{self.pause_seconds_left} s")

    def _draw_failed(self, painter, w, h):
        bg = QColor(185, 28, 28, 225) if self.system_failed_blink else QColor(127, 29, 29, 225)
        rect = QRectF(20, h * 0.14, w - 40, 110)
        painter.setPen(QPen(QColor("#FCA5A5"), 3))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 12, 12)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Helvetica", 20, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, t("system_failed"))
