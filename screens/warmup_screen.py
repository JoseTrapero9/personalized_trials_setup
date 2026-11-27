"""Interactive training warm-ups, before the training blocks (one task at a time, with coaching).

RadioWarmupScreen   the real radio game alone (no battery task, no checkpoints). The first
                    WARMUP_RADIO_CAPTIONED instructions are also shown as text while they are spoken and the
                    answer time is longer; afterwards listen only, at the real pace. After every instruction the
                    coach panel says what the radio said and which keys were right. Between instructions the
                    match rounds of the game can be practised.
BatteryWarmupScreen battery sums on screen (keys 1-4 put a colour in the next slot, Backspace = undo, the sum is
                    shown live) with a hint after a mistake and the answer after the 2nd one; then a short
                    delivery practice: D, then the button of the named point (F13 = point 1, F14 = point 2).

Nothing is evaluated or written to the CSV logs; markers start with TRAIN_ (training) and
Warmup_Start_<radio|battery> / Warmup_End_... frame them, so the camera PCs do not start a recording on them.
"""

import random

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config import (
    CUE_AUDIO_MAX_SECONDS,
    IDLE_HIT_POINTS,
    correct_audio,
    error_cue_audio,
    RESPONSE_SECONDS,
    WARMUP_BATTERY_PUZZLES,
    WARMUP_RADIO_CAPTIONED,
    WARMUP_RADIO_GAP_SECONDS,
    WARMUP_RADIO_PROBLEMS,
    WARMUP_RESPONSE_SECONDS,
)
from audio import audio_sys
from game import KEY_GLYPHS, RadioPanelGame
from radio import RadioPlayer
from lsl_markers import send_marker
from radio_script import LABELS
from state import state
from texts import t

COLOR_VALUES = {"Blue": 1, "Red": 2, "Yellow": 3, "Green": 4}
COLOR_HEX = {"Blue": "#2563EB", "Red": "#DC2626", "Yellow": "#EAB308", "Green": "#16A34A"}
COLOR_TEXT = {"Blue": "white", "Red": "white", "Yellow": "#1F2937", "Green": "white"}   # readable on the colour
SLOT_HEX = ["#111827", "#111827", "#111827"]     # slots all in black (x1 / x2 / x3)
TAG_PC = "color: white; background-color: #1D4ED8; border-radius: 12px; padding: 0 28px;"
TAG_WALK = "color: white; background-color: #C2410C; border-radius: 12px; padding: 0 28px;"
KEY_COLORS = {Qt.Key_1: "Blue", Qt.Key_2: "Red", Qt.Key_3: "Yellow", Qt.Key_4: "Green"}


def _panel():
    frame = QFrame()
    frame.setStyleSheet("background-color: white; border-radius: 12px;")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(22, 18, 22, 18)
    lay.setSpacing(14)
    return frame, lay


def _label(size, bold=False, color="#1E293B"):
    lbl = QLabel("")
    lbl.setFont(QFont("Helvetica", size, QFont.Bold if bold else QFont.Normal))
    lbl.setStyleSheet(f"color: {color};")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.RichText)
    return lbl


def _sound(ok):
    """Right / wrong sound of the warm-ups, always in the participant's headphones (Trekz)."""
    audio_sys.play_participant_clip(correct_audio if ok else error_cue_audio, CUE_AUDIO_MAX_SECONDS)


def _buttons(again_cb, continue_cb):
    row = QHBoxLayout()
    again = QPushButton("")
    cont = QPushButton("")
    for b, cb, color in ((again, again_cb, "#475569"), (cont, continue_cb, "#15803D")):
        b.setFont(QFont("Helvetica", 20, QFont.Bold))
        b.setFixedHeight(56)
        b.setStyleSheet(f"color: white; background-color: {color}; border-radius: 10px; padding: 0 24px;")
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(cb)
        row.addWidget(b)
    return row, again, cont


# ---------------------------------------------------------------------------
class RadioWarmupScreen(QWidget):
    def __init__(self, player_source=None):
        """player_source: the dual-task game, whose audio stream and clips are shared (one stream only)."""
        super().__init__()
        self.player_source = player_source
        self.finish_cb = None
        self.done_n = 0
        self.solved = 0
        self.finished = False
        self.setFocusPolicy(Qt.StrongFocus)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(14)
        self.game = RadioPanelGame()
        self.game.problem_done.connect(self._on_problem_done)
        lay.addWidget(self.game, stretch=6)

        panel, p = _panel()
        self.title = _label(28, True)
        self.intro = _label(18)
        self.stage = _label(18, True, "#B85C00")
        self.progress = _label(16, False, "#475467")
        self.caption = _label(24, True, "#0F172A")
        self.caption.setStyleSheet("color: #0F172A; background-color: #FEF9C3; border-radius: 10px; padding: 14px;")
        self.feedback = _label(20, True)
        self.between = _label(16, False, "#475467")
        for w in (self.title, self.intro, self.stage, self.progress, self.caption, self.feedback):
            p.addWidget(w)
        p.addStretch(1)
        p.addWidget(self.between)
        row, self.again_btn, self.cont_btn = _buttons(self.restart, self._continue)
        p.addLayout(row)
        lay.addWidget(panel, stretch=5)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)

    # ---------------- flow
    def start(self, finish_cb):
        self.finish_cb = finish_cb
        self.title.setText(t("wu_radio_title"))
        self.intro.setText(t("wu_radio_intro"))
        self.between.setText(t("wu_between", p=IDLE_HIT_POINTS))
        self.again_btn.setText(t("wu_again"))
        self.cont_btn.setText(t("wu_continue"))
        self.restart()

    def restart(self):
        self.done_n, self.solved, self.finished = 0, 0, False
        self.feedback.setText("")
        self._set_caption("")
        self.again_btn.hide()
        self.cont_btn.hide()
        send_marker("Warmup_Start_radio")
        g = self.game
        g.stop()
        src = self.player_source
        if src is not None:                            # one radio output stream for the whole program
            if src.player is None:
                src.player = RadioPlayer(device=audio_sys.participant_device)
            g.player, g.bank = src.player, src.bank
        g.score_offset = 0
        g.problem_gap = WARMUP_RADIO_GAP_SECONDS      # time to read the coaching (+ a match round) in between
        g.response_seconds = WARMUP_RESPONSE_SECONDS
        g.hud_label = t("wu_hud")
        g.start(order_offset=0)
        g.set_counting(False)                          # no checkpoints in the warm-up
        if src is not None:
            src.bank = g.bank                          # clips loaded once
        self.timer.start(100)
        self._refresh()
        self.setFocus()

    def _set_caption(self, text):
        self.caption.setText(text)
        self.caption.setVisible(bool(text))       # no empty yellow box (e.g. during the first match round)

    def _captioned(self):
        return self.done_n < WARMUP_RADIO_CAPTIONED

    def _refresh(self):
        if self.finished:
            return
        self.stage.setText(t("wu_stage_read") if self._captioned() else t("wu_stage_listen"))
        self.progress.setText(t("wu_progress", i=min(self.done_n + 1, WARMUP_RADIO_PROBLEMS),
                                n=WARMUP_RADIO_PROBLEMS, k=self.solved))
        p = self.game.problem
        if p is not None:
            self.feedback.setText("")
            if self._captioned():
                self._set_caption(f"“{self._spoken(p)}”")
            else:
                self._set_caption(t("wu_listen"))

    def _spoken(self, p):
        return " ".join(self.game.clip_texts.get(p["clip"], [""]))

    def _answer(self, p):
        lines = []
        words = LABELS.get(state.language, LABELS["en"])
        for n, ((kind, color), pos) in enumerate(zip(p["steps"], p["targets"]), start=1):
            key = "step_color" if kind == "C" else "step_word"
            lines.append(t(f"wu_{key}", n=n, x=words.get(color, color.upper()), key=KEY_GLYPHS[pos]))
        return "<br>".join(lines)

    def _on_problem_done(self, outcome, p):
        if self.finished or not self.isVisible():
            return
        self.done_n += 1
        if outcome == "solved":
            self.solved += 1
            self.feedback.setStyleSheet("color: #15803D;")
            self.feedback.setText(t("wu_solved"))
        else:
            self.feedback.setStyleSheet("color: #B42318;")
            self.feedback.setText(f"{t('wu_wrong') if outcome == 'wrong' else t('wu_timeout')}<br>{self._answer(p)}")
        self._set_caption(f"{t('wu_said')}<br>“{self._spoken(p)}”")
        send_marker(f"Warmup_Radio_Problem_{self.done_n}_{p['id']}_{outcome}")
        if self.done_n == WARMUP_RADIO_CAPTIONED:
            self.game.response_seconds = RESPONSE_SECONDS     # real pace from now on
        if self.done_n >= WARMUP_RADIO_PROBLEMS:
            QTimer.singleShot(2500, self._finish)       # let the last feedback clip play

    def _finish(self):
        self.finished = True
        self.timer.stop()
        self.game.stop()
        self.stage.setText("")
        self._set_caption(t("wu_radio_done", k=self.solved, n=WARMUP_RADIO_PROBLEMS))
        send_marker(f"Warmup_End_radio_Solved_{self.solved}_of_{WARMUP_RADIO_PROBLEMS}")
        self.again_btn.show()
        self.cont_btn.show()

    def _continue(self):
        if not self.finished:
            return
        self.timer.stop()
        self.game.stop()
        if self.finish_cb is not None:
            self.finish_cb()

    def stop(self):
        self.timer.stop()
        self.game.stop()

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        keys = {Qt.Key_Left: 0, Qt.Key_Down: 1, Qt.Key_Right: 2}
        if event.key() in keys and not self.finished:
            self.game.press(keys[event.key()])
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.finished:
            self._continue()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
def make_puzzles(n, seed="warmup"):
    """n battery tasks (target sum, instruction, answer) with the rules of generate_log_files.py."""
    from generate_log_files import all_answers, instruction_for, slot_sum
    rng = random.Random(seed)
    picked = rng.sample(all_answers(), n)
    return [(slot_sum(o), instruction_for(o), tuple(o)) for o in picked]


def calc_text(slots):
    parts = [f"{COLOR_VALUES[c]}×{m}" for c, m in zip(slots, (1, 2, 3))]
    return " + ".join(parts) + f" = {sum(COLOR_VALUES[c] * m for c, m in zip(slots, (1, 2, 3)))}"


class BatteryWarmupScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.finish_cb = None
        self.setFocusPolicy(Qt.StrongFocus)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 30, 60, 30)
        panel, p = _panel()
        outer.addWidget(panel)
        self.title = _label(30, True)
        p.addWidget(self.title)
        # where the participant works right now: ON THE PC (keyboard) or WALK TO POINT n (delivery buttons)
        self.tag = QLabel("")
        self.tag.setAlignment(Qt.AlignCenter)
        self.tag.setFont(QFont("Helvetica", 22, QFont.Bold))
        self.tag.setFixedHeight(56)
        p.addWidget(self.tag, alignment=Qt.AlignCenter)
        self.intro = _label(18)
        self.counter = _label(16, False, "#475467")
        p.addWidget(self.intro)
        p.addWidget(self.counter)

        body = QHBoxLayout()
        body.setSpacing(36)
        # left side: the battery values as a column of coloured chips (with their keys)
        values_col = QVBoxLayout()
        values_col.setSpacing(12)
        self.values_title = QLabel("")
        self.values_title.setFont(QFont("Helvetica", 22, QFont.Bold))
        self.values_title.setStyleSheet("color: #111827;")
        self.values_title.setAlignment(Qt.AlignCenter)
        values_col.addWidget(self.values_title)
        self.value_chips = {}
        for c in COLOR_VALUES:
            chip = QLabel("")
            chip.setTextFormat(Qt.RichText)
            chip.setAlignment(Qt.AlignCenter)
            chip.setFixedSize(230, 92)
            chip.setStyleSheet(f"color: {COLOR_TEXT[c]}; background-color: {COLOR_HEX[c]}; border-radius: 14px;")
            values_col.addWidget(chip)
            self.value_chips[c] = chip
        values_col.addStretch(1)
        body.addLayout(values_col)

        # right side: the task and the three slots (all in black), each with its multiplier on top
        main = QVBoxLayout()
        main.setSpacing(12)
        self.target = _label(34, True, "#222222")
        self.instr = _label(30, True, "#0056B3")
        main.addWidget(self.target)
        main.addWidget(self.instr)
        slots_row = QHBoxLayout()
        slots_row.addStretch(1)
        self.slot_boxes, self.slot_heads = [], []
        for k in range(3):
            col = QVBoxLayout()
            col.setSpacing(6)
            head = QLabel("")
            head.setTextFormat(Qt.RichText)
            head.setAlignment(Qt.AlignCenter)
            head.setFixedSize(220, 64)
            head.setStyleSheet(f"color: white; background-color: {SLOT_HEX[k]}; border-radius: 12px;")
            box = QLabel("")
            box.setFixedSize(220, 160)
            box.setAlignment(Qt.AlignCenter)
            box.setFont(QFont("Helvetica", 20, QFont.Bold))
            box.setTextFormat(Qt.RichText)
            col.addWidget(head)
            col.addWidget(box)
            slots_row.addLayout(col)
            slots_row.addSpacing(24)
            self.slot_heads.append(head)
            self.slot_boxes.append(box)
        slots_row.addStretch(1)
        main.addLayout(slots_row)
        self.sum_now = _label(26, True, "#111827")
        self.feedback = _label(22, True)
        main.addWidget(self.sum_now)
        main.addWidget(self.feedback)
        main.addStretch(1)
        body.addLayout(main, stretch=1)
        p.addLayout(body, stretch=1)
        row, self.again_btn, self.cont_btn = _buttons(self.restart, self._continue)
        p.addLayout(row)

    # ---------------- flow
    def start(self, finish_cb):
        self.finish_cb = finish_cb
        self.title.setText(t("wu_battery_title"))
        self.again_btn.setText(t("wu_again"))
        self.cont_btn.setText(t("wu_continue"))
        self.restart()

    def restart(self):
        self.puzzles = make_puzzles(WARMUP_BATTERY_PUZZLES)
        self.idx, self.first_try_ok = 0, 0
        self.stage = "puzzle"                 # puzzle -> deliver_d -> deliver_pt -> done
        self.again_btn.hide()
        self.cont_btn.hide()
        send_marker("Warmup_Start_battery")
        self._new_puzzle()
        self.setFocus()

    def _new_puzzle(self):
        self.slots, self.tries, self.solved = [], 0, False
        total, instr, _ = self.puzzles[self.idx]
        self.intro.setText(t("wu_battery_intro"))
        self._set_tag(pc=True)
        self.counter.setText(t("wu_puzzle", i=self.idx + 1, n=len(self.puzzles)))
        self.target.setText(f"Sum must be {total}")
        self.instr.setText(self._instr_text(instr))
        self.feedback.setText("")
        self._draw_slots()

    @staticmethod
    def _instr_text(instr):
        return instr          # English colour names, exactly as the real battery task shows them

    def _draw_legend(self):
        self.values_title.setText(t("wu_values"))
        for n, (c, chip) in enumerate(self.value_chips.items(), start=1):
            chip.setText(f"<span style='font-size:22pt; font-weight:bold'>{c} = {COLOR_VALUES[c]}</span>"
                         f"<br><span style='font-size:13pt'>{t('wu_key', n=n)}</span>")
        for k, head in enumerate(self.slot_heads):
            head.setText(f"<span style='font-size:15pt; font-weight:bold'>{t('wu_slot', n=k + 1)}</span>"
                         f"&nbsp;&nbsp;<span style='font-size:26pt; font-weight:bold'>×{k + 1}</span>")

    def _draw_slots(self):
        self._draw_legend()
        for k, box in enumerate(self.slot_boxes):
            if k < len(self.slots):
                c = self.slots[k]
                box.setText(f"<span style='font-size:26pt'>{c}</span><br>"
                            f"{COLOR_VALUES[c]} × {k + 1} = <b>{COLOR_VALUES[c] * (k + 1)}</b>")
                box.setStyleSheet(f"color: {COLOR_TEXT[c]}; background-color: {COLOR_HEX[c]}; border-radius: 14px;"
                                  f"border: 5px solid {SLOT_HEX[k]};")
            else:
                box.setText(f"<span style='font-size:16pt'>{t('wu_slot_empty')}</span><br>"
                            f"<span style='font-size:40pt'>? × {k + 1}</span>")
                box.setStyleSheet(f"color: {SLOT_HEX[k]}; background-color: #F8FAFC; border-radius: 14px;"
                                  f"border: 5px dashed {SLOT_HEX[k]};")
        total = self.puzzles[self.idx][0] if self.stage == "puzzle" else 0
        s = sum(COLOR_VALUES[c] * (k + 1) for k, c in enumerate(self.slots))
        self.sum_now.setText(t("wu_sum_now", s=s, t=total) if self.stage == "puzzle" else "")

    def _place(self, color):
        if self.stage != "puzzle" or self.solved or len(self.slots) >= 3:
            return
        self.slots.append(color)
        self._draw_slots()
        if len(self.slots) == 3:
            self._check()

    def _check(self):
        total, instr, answer = self.puzzles[self.idx]
        self.tries += 1
        slots = tuple(self.slots)
        ok = slots == answer
        result = "correct" if ok else ("order" if sorted(slots) == sorted(answer) else "colors")
        send_marker(f"Warmup_Battery_Puzzle_{self.idx + 1}_Try_{self.tries}_{result}_{'-'.join(slots)}")
        _sound(ok)
        if ok:
            self.solved = True
            if self.tries == 1:
                self.first_try_ok += 1
            self.feedback.setStyleSheet("color: #15803D;")
            self.feedback.setText(t("wu_b_correct", calc=calc_text(slots)) + f"<br><small>{t('wu_b_next')}</small>")
            return
        self.feedback.setStyleSheet("color: #B42318;")
        msg = (t("wu_b_order", calc=calc_text(slots)) if result == "order"
               else t("wu_b_colors", instr=self._instr_text(instr)))
        if self.tries >= 2:                         # second mistake: show the answer
            ans = " · ".join(answer)
            msg += "<br>" + t("wu_b_answer", ans=ans, calc=calc_text(answer))
        self.feedback.setText(msg)
        QTimer.singleShot(1200, self._clear_after_mistake)

    def _clear_after_mistake(self):
        if self.stage == "puzzle" and not self.solved and len(self.slots) == 3:
            self.slots = []
            self._draw_slots()

    def _next(self):
        if self.stage == "puzzle" and self.solved:
            if self.idx + 1 < len(self.puzzles):
                self.idx += 1
                self._new_puzzle()
            else:
                self._start_delivery()

    # ---------------- delivery practice: D, then point 1; D, then point 2
    def _start_delivery(self):
        self.stage, self.deliver_point = "deliver_d", 1
        self.title.setText(t("wu_deliver_title"))
        self.intro.setText("")
        self.counter.setText("")
        self.target.setText("")
        self.instr.setText(t("wu_deliver_d"))
        self._set_tag(pc=True)
        self.feedback.setText("")
        self.slots = list(self.puzzles[-1][2])
        self._draw_slots()

    def _set_tag(self, pc=True):
        if pc:
            self.tag.setText(t("wu_tag_pc"))
            self.tag.setStyleSheet(TAG_PC)
        else:
            pt, side = self._point_names()
            self.tag.setText(t("wu_tag_walk", pt=pt.upper(), key=side))
            self.tag.setStyleSheet(TAG_WALK)
        self.tag.show()

    def _point_names(self):
        n = self.deliver_point
        return t("point", n=n), t("key_left") if n == 1 else t("key_right")

    def on_deliver_key(self):
        if self.stage == "deliver_d":
            self.stage = "deliver_pt"
            pt, key = self._point_names()
            self.instr.setText(t("wu_deliver_pt", pt=pt, key=key))
            self._set_tag(pc=False)                      # now away from the PC: walk to the point
            self.feedback.setText("")
            send_marker(f"Warmup_Delivery_D_Point_{self.deliver_point}")

    def on_point_key(self, point):
        """F13 = point 1, F14 = point 2 (routed here by the controller)."""
        if self.stage != "deliver_pt":
            return
        pt, key = self._point_names()
        ok = point == self.deliver_point
        send_marker(f"Warmup_Delivery_Pressed_{point}_Expected_{self.deliver_point}_{'correct' if ok else 'wrong'}")
        _sound(ok)
        if not ok:
            self.feedback.setStyleSheet("color: #B42318;")
            self.feedback.setText(t("wu_deliver_bad", pt=pt, key=key))
            return
        self.feedback.setStyleSheet("color: #15803D;")
        self.feedback.setText(t("wu_deliver_ok"))
        if self.deliver_point == 1:
            self.deliver_point, self.stage = 2, "deliver_d"
            QTimer.singleShot(1200, self._back_to_pc_for_d)
        else:
            self.stage = "done"
            QTimer.singleShot(1000, self._finish)

    def _back_to_pc_for_d(self):
        self.instr.setText(t("wu_deliver_d"))
        self.feedback.setText("")
        self._set_tag(pc=True)

    def _finish(self):
        self.tag.hide()
        self.title.setText(t("wu_battery_title"))
        self.instr.setText(t("wu_battery_done", k=self.first_try_ok, n=len(self.puzzles)))
        send_marker(f"Warmup_End_battery_FirstTry_{self.first_try_ok}_of_{len(self.puzzles)}")
        self.again_btn.show()
        self.cont_btn.show()

    def _continue(self):
        if self.stage == "done" and self.finish_cb is not None:
            self.finish_cb()

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        k = event.key()
        if k in KEY_COLORS:
            self._place(KEY_COLORS[k])
        elif k == Qt.Key_Backspace and self.stage == "puzzle" and not self.solved and self.slots:
            self.slots.pop()
            self._draw_slots()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            if self.stage == "done":
                self._continue()
            else:
                self._next()
        elif k == Qt.Key_D:
            self.on_deliver_key()
        else:
            super().keyPressEvent(event)
