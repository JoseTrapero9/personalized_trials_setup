"""Pre-condition screen with instructions and the start countdown."""

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from config import (
    DELIVERY_WINDOW_SECONDS,
    IDLE_HIT_POINTS,
    MAX_ROUNDS_PER_CONDITION,
    PROBLEMS_PER_CHECKPOINT,
    RETRIEVAL_SECONDS,
    TRAINING_ROUNDS
)
from lsl_markers import send_marker
from robot import start_robot_process
from state import state
from texts import t


class startscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.ticks_left = 5
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(25)

        main_font = QFont("Helvetica", 24)
        button_font = QFont("Helvetica", 26, QFont.Bold)
        timer_font = QFont("Helvetica", 72, QFont.Bold)

        self.message_label = QLabel()
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.countdown_label = QLabel("")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.hide()
        layout.addWidget(self.countdown_label)

        self.start_button = QPushButton("Start")
        self.start_button.setFont(button_font)
        self.start_button.setFixedWidth(300)
        self.start_button.setFixedHeight(65)
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def configure_for_condition(self, cond_name):
        rounds = TRAINING_ROUNDS if cond_name == "training" else MAX_ROUNDS_PER_CONDITION
        title = t("start_title_training") if cond_name == "training" else t("start_title_cond", c=cond_name.upper())
        self.message_label.setText(
            f"<b>{title}</b><br><br>"
            + t("start_body", n=PROBLEMS_PER_CHECKPOINT, r=RETRIEVAL_SECONDS,
                d=DELIVERY_WINDOW_SECONDS, rounds=rounds)
            + (t("start_hard_line", p=IDLE_HIT_POINTS) if state.game_mode == "hard" else "")
        )
        self.start_button.setText(t("start_button"))
        self.start_button.show()
        self.countdown_label.hide()

    def on_start_clicked(self):
        send_marker("Robot_Started_Waiting")
        start_robot_process()

        self.ticks_left = 5
        self.start_button.hide()
        self.message_label.setText(t("preparing"))
        self.countdown_label.setText(f"{self.ticks_left} s")
        self.countdown_label.show()
        self.timer.start(1000)

    def timer_tick(self):
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.timer.stop()
            self.switch_callback()
        else:
            self.countdown_label.setText(f"{self.ticks_left} s")
