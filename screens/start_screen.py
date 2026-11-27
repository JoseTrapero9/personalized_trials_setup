"""Pre-condition screen with instructions and the pre-task fixation cross."""

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from config import (
    DELIVERY_WINDOW_SECONDS,
    MAX_ROUNDS_PER_CONDITION,
    PROBLEMS_PER_CHECKPOINT,
    RETRIEVAL_SECONDS,
    START_FIXATION_SECONDS,
    TRAINING_CONDITIONS,
    TRAINING_ROUNDS
)
from lsl_markers import send_marker
from robot import start_robot_process
from state import state
from texts import block_name, t


class startscreen(QWidget):
    def __init__(self, switch_callback, on_start_callback=None):
        super().__init__()
        self.switch_callback = switch_callback
        self.on_start_callback = on_start_callback
        self.ticks_left = START_FIXATION_SECONDS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(25)

        main_font = QFont("Helvetica", 24)
        button_font = QFont("Helvetica", 26, QFont.Bold)
        fixation_font = QFont("Helvetica", 120, QFont.Bold)

        self.message_label = QLabel()
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.fixation_label = QLabel("+")
        self.fixation_label.setFont(fixation_font)
        self.fixation_label.setAlignment(Qt.AlignCenter)
        self.fixation_label.hide()
        layout.addWidget(self.fixation_label)

        self.start_button = QPushButton("Start")
        self.start_button.setFont(button_font)
        self.start_button.setFixedWidth(300)
        self.start_button.setFixedHeight(65)
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def configure_for_condition(self, cond_name):
        self.timer.stop()
        rounds = TRAINING_ROUNDS if cond_name == "training" else MAX_ROUNDS_PER_CONDITION
        if cond_name == "training":
            title = t("start_title_block", i=state.training_block + 1, n=len(TRAINING_CONDITIONS),
                      name=block_name(state.training_condition))
        else:
            title = t("start_title_cond", c=cond_name.upper())
        self.message_label.setText(
            f"<b>{title}</b><br><br>"
            + t("start_body", n=PROBLEMS_PER_CHECKPOINT, r=RETRIEVAL_SECONDS,
                d=DELIVERY_WINDOW_SECONDS, rounds=rounds)
        )
        self.message_label.show()
        self.start_button.setText(t("start_button"))
        self.start_button.show()
        self.fixation_label.hide()

    def on_start_clicked(self):
        send_marker("Robot_Started_Waiting")
        start_robot_process()
        if self.on_start_callback is not None:
            self.on_start_callback()

        if START_FIXATION_SECONDS <= 0:
            self.switch_callback()
            return

        self.ticks_left = START_FIXATION_SECONDS
        self.start_button.hide()
        self.message_label.hide()
        self.fixation_label.show()
        send_marker("Fixation_Start")
        self.timer.start(1000)

    def timer_tick(self):
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.timer.stop()
            send_marker("Fixation_End")
            self.switch_callback()
