"""Slide screen: the task tutorial before training, and the cue slide before every training block."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config import (
    DELIVERY_WINDOW_SECONDS,
    FAIL_PENALTY,
    HARD_INSTRUCTION_MULTIPLIER,
    HARD_PENALTY_MULTIPLIER,
    IDLE_HIT_POINTS,
    POINTS_PER_STEP,
    PROBLEMS_PER_CHECKPOINT,
    RETRIEVAL_SECONDS,
    TASK_SECONDS_DEFAULT,
    TRAINING_CONDITIONS,
    TRAINING_ROUNDS,
)
from lsl_markers import send_marker
from state import state
from texts import HARD_TUTORIAL_STEP, TUTORIAL, block_name, cue_slide, t


class tutorialscreen(QWidget):
    def __init__(self, finish_callback, demo_callback=None):
        """finish_callback: after the task tutorial. demo_callback(condition, is_correct): plays a sample cue."""
        super().__init__()
        self.finish_callback = finish_callback
        self.demo_callback = demo_callback
        self._on_finish = finish_callback
        self.current_step = 0
        self.steps = []
        self.header_fn = None
        self.last_label = ""
        self.demo_condition = None
        self.marker = "Tutorial_Finished"
        self.setFocusPolicy(Qt.StrongFocus)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 50, 80, 50)
        layout.setSpacing(25)

        self.step_label = QLabel("")
        self.step_label.setFont(QFont("Helvetica", 18, QFont.Bold))
        self.step_label.setStyleSheet("color: #B85C00;")
        layout.addWidget(self.step_label, alignment=Qt.AlignCenter)

        self.title_label = QLabel("")
        self.title_label.setFont(QFont("Helvetica", 36, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.body_label = QLabel("")
        self.body_label.setFont(QFont("Helvetica", 24))
        self.body_label.setAlignment(Qt.AlignCenter)
        self.body_label.setWordWrap(True)
        layout.addWidget(self.body_label, stretch=1)

        # sample cues on the cue slides (also keys 1 / 2)
        demo_row = QHBoxLayout()
        demo_row.addStretch(1)
        self.demo_pos_btn = QPushButton("")
        self.demo_neg_btn = QPushButton("")
        for b, ok, color in ((self.demo_pos_btn, True, "#15803D"), (self.demo_neg_btn, False, "#B42318")):
            b.setFont(QFont("Helvetica", 20, QFont.Bold))
            b.setFixedSize(300, 56)
            b.setStyleSheet(f"color: white; background-color: {color}; border-radius: 10px;")
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, ok=ok: self.play_demo(ok))
            demo_row.addWidget(b)
            demo_row.addSpacing(30)
        demo_row.addStretch(1)
        layout.addLayout(demo_row)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.next_btn = QPushButton("Next →")
        for b in (self.back_btn, self.next_btn):
            b.setFont(QFont("Helvetica", 22, QFont.Bold))
            b.setFixedSize(260, 60)
            b.setFocusPolicy(Qt.NoFocus)
        self.back_btn.clicked.connect(self.prev_step)
        self.next_btn.clicked.connect(self.next_step)
        nav.addWidget(self.back_btn)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)

        self._update_page()

    # ------------------------------------------------------------------ content
    def reset(self):
        """Task tutorial (radio + battery) in the participant's language, from the first page."""
        blocks = "<br>".join(f"{i}. {block_name(c)}" for i, c in enumerate(TRAINING_CONDITIONS, start=1))
        fmt = dict(n=PROBLEMS_PER_CHECKPOINT, r=RETRIEVAL_SECONDS, d=DELIVERY_WINDOW_SECONDS, p=IDLE_HIT_POINTS,
                   ip=POINTS_PER_STEP * HARD_INSTRUCTION_MULTIPLIER, fp=FAIL_PENALTY * HARD_PENALTY_MULTIPLIER,
                   s=TASK_SECONDS_DEFAULT, b=len(TRAINING_CONDITIONS), k=TRAINING_ROUNDS, blocks=blocks)
        steps = list(TUTORIAL.get(state.language, TUTORIAL["en"]))
        steps.insert(4, HARD_TUTORIAL_STEP.get(state.language, HARD_TUTORIAL_STEP["en"]))   # the only game mode
        self.body_label.setFont(QFont("Helvetica", 24))
        self._load([(title, body.format(**fmt) if "{" in body else body) for title, body in steps],
                   self.finish_callback, lambda i, n: t("tut_header", i=i, n=n), t("tut_continue"),
                   None, "Tutorial_Finished")

    def show_cue_slide(self, condition, block_index, n_blocks, finish_cb):
        """One slide explaining the feedback of a training block, with sample cues."""
        title, body = cue_slide(condition, state.language, state.audio_cue_mode)
        demo = condition if (self.demo_callback is not None and condition != "baseline") else None
        self.body_label.setFont(QFont("Helvetica", 22))
        self._load([(title, body)], finish_cb,
                   lambda i, n: t("block_header", i=block_index + 1, n=n_blocks), t("block_start"),
                   demo, f"Cue_Slide_Finished_{condition}")
        send_marker(f"Cue_Slide_Shown_Block_{block_index + 1}_{condition}")

    def _load(self, steps, on_finish, header_fn, last_label, demo_condition, marker):
        self.steps, self._on_finish, self.header_fn = steps, on_finish, header_fn
        self.last_label, self.demo_condition, self.marker = last_label, demo_condition, marker
        self.back_btn.setText(t("tut_back"))
        self.demo_pos_btn.setText(t("demo_pos"))
        self.demo_neg_btn.setText(t("demo_neg"))
        self.current_step = 0
        self._update_page()

    def _update_page(self):
        if not self.steps:
            return
        title, body = self.steps[self.current_step]
        self.step_label.setText(self.header_fn(self.current_step + 1, len(self.steps)))
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.back_btn.setVisible(len(self.steps) > 1)
        self.back_btn.setEnabled(self.current_step > 0)
        last = self.current_step == len(self.steps) - 1
        self.next_btn.setText(self.last_label if last else t("tut_next"))
        for b in (self.demo_pos_btn, self.demo_neg_btn):
            b.setVisible(self.demo_condition is not None)

    # ------------------------------------------------------------------ navigation
    def play_demo(self, is_correct):
        if self.demo_condition is not None and self.demo_callback is not None:
            send_marker(f"Cue_Demo_{self.demo_condition}_{'correct' if is_correct else 'incorrect'}")
            self.demo_callback(self.demo_condition, is_correct)

    def next_step(self):
        if self.current_step >= len(self.steps) - 1:
            send_marker(self.marker)
            self._on_finish()
        else:
            self.current_step += 1
            self._update_page()

    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self._update_page()

    def on_point_key(self, point: int):
        if point == 2:
            self.next_step()
        else:
            self.prev_step()

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        if event.key() in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Up, Qt.Key_Return, Qt.Key_Enter):
            self.next_step()
        elif event.key() == Qt.Key_Left:
            self.prev_step()
        elif event.key() == Qt.Key_1:
            self.play_demo(True)
        elif event.key() == Qt.Key_2:
            self.play_demo(False)
