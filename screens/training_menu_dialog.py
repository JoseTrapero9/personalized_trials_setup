"""Researcher dialog when "training" is started: where to start (e.g. after a crash), and whether to go on."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                             QVBoxLayout)

from config import TRAINING_CONDITIONS, TRAINING_ROUNDS
from texts import block_name

# the training parts, in order
TRAINING_PARTS = ["tutorial", "warmup_radio", "warmup_battery"] + [f"block{i}" for i in range(len(TRAINING_CONDITIONS))]


def part_label(part):
    if part == "tutorial":
        return "Tutorial slides (both tasks)"
    if part == "warmup_radio":
        return "Warm-up: radio only (with text, then listening only)"
    if part == "warmup_battery":
        return "Warm-up: battery sums on screen + delivery practice"
    i = int(part[5:])
    cond = TRAINING_CONDITIONS[i]
    return f"Block {i + 1}: {cond} ({block_name(cond, 'en')}), {TRAINING_ROUNDS} rounds"


class TrainingMenuDialog(QDialog):
    """exec_() == Accepted -> .start_index (index in TRAINING_PARTS) and .only_this (bool)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Training: where to start")
        self.setMinimumWidth(760)
        self.start_index, self.only_this = 0, False
        lay = QVBoxLayout(self)
        title = QLabel("Start the training at:")
        title.setFont(QFont("Helvetica", 18, QFont.Bold))
        lay.addWidget(title)
        self.list = QListWidget()
        self.list.setFont(QFont("Helvetica", 16))
        for part in TRAINING_PARTS:
            QListWidgetItem(part_label(part), self.list)
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self._accept())
        lay.addWidget(self.list)
        self.only = QCheckBox("Only this part (back to the menu afterwards)")
        self.only.setFont(QFont("Helvetica", 15))
        lay.addWidget(self.only)
        hint = QLabel("Default: from the start, all parts in order. Choose a later part to continue after a "
                      "problem; the robot always starts at point 1 in every block.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #475467;")
        lay.addWidget(hint)
        row = QHBoxLayout()
        back = QPushButton("Back to the menu")
        start = QPushButton("Start")
        start.setDefault(True)
        for b in (back, start):
            b.setFont(QFont("Helvetica", 16, QFont.Bold))
            b.setFixedHeight(46)
        back.clicked.connect(self.reject)
        start.clicked.connect(self._accept)
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(start)
        lay.addLayout(row)

    def _accept(self):
        self.start_index = max(0, self.list.currentRow())
        self.only_this = self.only.isChecked()
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept()
        else:
            super().keyPressEvent(event)
