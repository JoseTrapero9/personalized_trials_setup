"""Researcher setup screen (subject + condition)."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget

import json
import os

from config import ALL_CONDITIONS, GAME_MODES, MAX_ROUNDS_PER_CONDITION, PROBLEMS_PER_CHECKPOINT, RADIO_AUDIO_DIR
from lsl_markers import send_marker
from radio_script import LANGUAGES
from state import state


class setupscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        main_font = QFont("Helvetica", 24)
        title_font = QFont("Helvetica", 30, QFont.Bold)

        self.title_label = QLabel("Dual-Task Experiment Configuration")
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)

        self.subj_label = QLabel("Subject Number:")
        self.subj_label.setFont(main_font)
        layout.addWidget(self.subj_label, alignment=Qt.AlignCenter)

        self.subj_combo = QComboBox()
        self.subj_combo.setFont(main_font)
        self.subj_combo.setFixedWidth(320)
        for i in range(1, 100):
            self.subj_combo.addItem(str(i))
        layout.addWidget(self.subj_combo, alignment=Qt.AlignCenter)

        self.cond_label = QLabel("Select Mode / Condition:")
        self.cond_label.setFont(main_font)
        layout.addWidget(self.cond_label, alignment=Qt.AlignCenter)

        self.cond_combo = QComboBox()
        self.cond_combo.setFont(main_font)
        self.cond_combo.setFixedWidth(320)
        self.cond_combo.addItems(ALL_CONDITIONS)
        layout.addWidget(self.cond_combo, alignment=Qt.AlignCenter)

        self.mode_label = QLabel("Game Mode:")
        self.mode_label.setFont(main_font)
        layout.addWidget(self.mode_label, alignment=Qt.AlignCenter)

        self.mode_combo = QComboBox()
        self.mode_combo.setFont(main_font)
        self.mode_combo.setFixedWidth(320)
        for mode in GAME_MODES:
            self.mode_combo.addItem(mode.capitalize(), mode)
        layout.addWidget(self.mode_combo, alignment=Qt.AlignCenter)

        self.lang_label = QLabel("Participant Language (radio + screens):")
        self.lang_label.setFont(main_font)
        layout.addWidget(self.lang_label, alignment=Qt.AlignCenter)

        self.lang_combo = QComboBox()
        self.lang_combo.setFont(main_font)
        self.lang_combo.setFixedWidth(320)
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.currentIndexChanged.connect(self._update_audio_status)
        layout.addWidget(self.lang_combo, alignment=Qt.AlignCenter)

        self.audio_status = QLabel("")
        self.audio_status.setFont(QFont("Helvetica", 15))
        self.audio_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.audio_status, alignment=Qt.AlignCenter)

        info_lbl = QLabel(
            f"Each condition runs for {MAX_ROUNDS_PER_CONDITION} battery rounds.\n"
            f"A checkpoint (5s retrieval pause) follows every {PROBLEMS_PER_CHECKPOINT} radio problems.\n"
            f"Say 'DELIVER' (or press D) for a 5s delivery pause."
        )
        info_lbl.setFont(QFont("Helvetica", 16))
        info_lbl.setStyleSheet("color: #555;")
        info_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_lbl, alignment=Qt.AlignCenter)

        self.continue_button = QPushButton("Start Selected Mode")
        self.continue_button.setFont(main_font)
        self.continue_button.setFixedWidth(320)
        self.continue_button.setFixedHeight(60)
        self.continue_button.clicked.connect(self.save_and_continue)
        layout.addWidget(self.continue_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)
        self._update_audio_status()

    def _update_audio_status(self):
        code = self.lang_combo.currentData()
        path = os.path.join(RADIO_AUDIO_DIR, code, "manifest.json")
        try:
            with open(path, encoding="utf-8") as f:
                m = json.load(f)
            self.audio_status.setText(f"Radio audio OK: {len(m.get('clips', {}))} clips, voice {m.get('voice')}")
            self.audio_status.setStyleSheet("color: #15803D;")
        except Exception:
            self.audio_status.setText(f"Radio audio MISSING: run  python generate_radio_audio.py --lang {code}")
            self.audio_status.setStyleSheet("color: #B42318; font-weight: bold;")

    def save_and_continue(self):

        state.subject_number = self.subj_combo.currentText()
        state.current_condition = self.cond_combo.currentText()
        state.training_active = (state.current_condition == "training")
        state.language = self.lang_combo.currentData()
        state.game_mode = self.mode_combo.currentData()

        if state.current_condition in ["training", "baseline"]:
            state.difficulty = "easy"
        else:
            state.difficulty = "hard"

        send_marker(f"Setup_Complete_Subj_{state.subject_number}_Cond_{state.current_condition}_Lang_{state.language}_Mode_{state.game_mode}")
        self.switch_callback()
