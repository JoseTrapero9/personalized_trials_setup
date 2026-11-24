"""Researcher check before a run starts: who, what, files that would be overwritten, and whether the
headphones, the vest, the camera PC and LSL are ready. Refreshes twice a second, so a vest or camera PC
that connects while it is open turns green. Start anyway is possible; with a red line the default is Go back."""

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

COLORS = {"info": "#1F2937", "ok": "#15803D", "warn": "#B45309", "fail": "#B42318"}
MARKS = {"info": "", "ok": "OK  ", "warn": "!  ", "fail": "X  "}
ROW_WIDTH = 1040


class PreflightDialog(QDialog):
    def __init__(self, title, rows_fn, parent=None):
        """rows_fn() -> [(level, text)], called again every 500 ms."""
        super().__init__(parent)
        self.rows_fn = rows_fn
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(1100)
        self.setStyleSheet("QDialog { background: #F8FAFC; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(14)
        head = QLabel(title)
        head.setFont(QFont("Helvetica", 24, QFont.Bold))
        lay.addWidget(head)
        self.rows_box = QVBoxLayout()            # one label per check, so a long line can never be cut off
        self.rows_box.setSpacing(6)
        lay.addLayout(self.rows_box)
        self.row_labels = []
        self.summary = QLabel("")
        self.summary.setFont(QFont("Helvetica", 17, QFont.Bold))
        lay.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.back_btn = QPushButton("Go back")
        self.start_btn = QPushButton("Start")
        for b in (self.back_btn, self.start_btn):
            b.setFont(QFont("Helvetica", 18, QFont.Bold))
            b.setMinimumSize(220, 54)
        self.back_btn.clicked.connect(self.reject)
        self.start_btn.clicked.connect(self.accept)
        buttons.addWidget(self.back_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.start_btn)
        lay.addLayout(buttons)
        self.levels = []
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)

    def refresh(self):
        rows = self.rows_fn()
        self.levels = [level for level, _ in rows]
        resized = len(rows) != len(self.row_labels)
        while len(self.row_labels) < len(rows):
            label = QLabel("")
            label.setWordWrap(True)
            label.setFixedWidth(ROW_WIDTH)
            self.rows_box.addWidget(label)
            self.row_labels.append(label)
        while len(self.row_labels) > len(rows):
            self.row_labels.pop().deleteLater()
        for label, (level, text) in zip(self.row_labels, rows):
            label.setText(MARKS[level] + text)
            label.setFont(QFont("Helvetica", 17, QFont.Normal if level == "info" else QFont.Bold))
            label.setStyleSheet(f"color: {COLORS[level]};")
            height = label.heightForWidth(ROW_WIDTH)            # wrapped lines get their full height
            if label.minimumHeight() != height:
                label.setMinimumHeight(height)
                resized = True
        fails, warns = self.levels.count("fail"), self.levels.count("warn")
        if fails:
            self.summary.setText(f"{fails} problem(s) above. Fix them, or start anyway if you know why.")
            self.summary.setStyleSheet(f"color: {COLORS['fail']};")
            self.start_btn.setText("Start anyway")
            self.back_btn.setDefault(True)
        else:
            self.summary.setText("Ready." + (f"  Check the {warns} warning(s)." if warns else ""))
            self.summary.setStyleSheet(f"color: {COLORS['warn' if warns else 'ok']};")
            self.start_btn.setText("Start")
            self.start_btn.setDefault(True)
        if resized:
            self.adjustSize()

    def done(self, result):
        self.timer.stop()
        super().done(result)
