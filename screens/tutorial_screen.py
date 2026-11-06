"""Step-by-step tutorial screen."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config import DELIVERY_WINDOW_SECONDS, IDLE_HIT_POINTS, PROBLEMS_PER_CHECKPOINT, RETRIEVAL_SECONDS
from lsl_markers import send_marker
from state import state
from texts import HARD_TUTORIAL_STEP, TUTORIAL, t


class tutorialscreen(QWidget):
    def __init__(self, finish_callback):
        super().__init__()
        self.finish_callback = finish_callback
        self.current_step = 0
        self.steps = []
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

        nav = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.next_btn = QPushButton("Next →")
        for b in (self.back_btn, self.next_btn):
            b.setFont(QFont("Helvetica", 22, QFont.Bold))
            b.setFixedSize(220, 60)
        self.back_btn.clicked.connect(self.prev_step)
        self.next_btn.clicked.connect(self.next_step)
        nav.addWidget(self.back_btn)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)

        self._update_page()

    def reset(self):
        """Load the steps in the participant's language and go to the first page."""
        fmt = dict(n=PROBLEMS_PER_CHECKPOINT, r=RETRIEVAL_SECONDS, d=DELIVERY_WINDOW_SECONDS)
        fmt["p"] = IDLE_HIT_POINTS
        steps = list(TUTORIAL.get(state.language, TUTORIAL["en"]))
        if state.game_mode == "hard":
            steps.insert(4, HARD_TUTORIAL_STEP.get(state.language, HARD_TUTORIAL_STEP["en"]))
        self.steps = [(title, body.format(**fmt) if "{" in body else body) for title, body in steps]
        self.back_btn.setText(t("tut_back"))
        self.current_step = 0
        self._update_page()

    def _update_page(self):
        if not self.steps:
            return
        title, body = self.steps[self.current_step]
        self.step_label.setText(t("tut_header", i=self.current_step + 1, n=len(self.steps)))
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.back_btn.setEnabled(self.current_step > 0)
        self.next_btn.setText(t("tut_start") if self.current_step == len(self.steps) - 1 else t("tut_next"))

    def next_step(self):
        if self.current_step >= len(self.steps) - 1:
            send_marker("Tutorial_Finished")
            self.finish_callback()
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
        if event.key() in (Qt.Key_Right, Qt.Key_Up):
            self.next_step()
        elif event.key() == Qt.Key_Left:
            self.prev_step()
