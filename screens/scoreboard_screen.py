"""Arcade-style scoreboard shown after each condition."""

import json
import os
import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from config import base_dir
from lsl_markers import send_marker
from state import state


class ArcadeScoreboardScreen(QWidget):
    def __init__(self, finish_callback):
        super().__init__()
        self.finish_callback = finish_callback
        self.condition_name = "baseline"
        self.final_score = 0
        self.letters = [0, 0, 0]   # Indices 0..25 ('A'..'Z')
        self.slot_idx = 0          # 0, 1, 2 for letter entry; 3 = leaderboard view
        self.alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        self.setFocusPolicy(Qt.StrongFocus)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("background-color: #090D16; color: #F8FAFC;")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(22)

        self.title_label = QLabel("ARCADE HIGH SCORES")
        self.title_label.setFont(QFont("Courier", 42, QFont.Bold))
        self.title_label.setStyleSheet("color: #FACC15; letter-spacing: 4px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.score_label = QLabel("YOUR SCORE: 0000")
        self.score_label.setFont(QFont("Courier", 34, QFont.Bold))
        self.score_label.setStyleSheet("color: #38BDF8;")
        self.score_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.score_label)

        self.prompt_label = QLabel(
            "ENTER YOUR INITIALS\n[LEFT / RIGHT ARROW] = Select Letter    [UP ARROW] = Confirm"
        )
        self.prompt_label.setFont(QFont("Courier", 20, QFont.Bold))
        self.prompt_label.setStyleSheet("color: #A3E635;")
        self.prompt_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.prompt_label)

        # 3-letter arcade selector
        slots_holder = QWidget()
        slots_layout = QHBoxLayout(slots_holder)
        slots_layout.setSpacing(24)
        slots_layout.setAlignment(Qt.AlignCenter)

        self.letter_labels = []
        for _ in range(3):
            lbl = QLabel("A")
            lbl.setFont(QFont("Courier", 64, QFont.Bold))
            lbl.setFixedSize(110, 130)
            lbl.setAlignment(Qt.AlignCenter)
            slots_layout.addWidget(lbl)
            self.letter_labels.append(lbl)

        layout.addWidget(slots_holder)

        # Leaderboard table display
        self.board_label = QLabel("")
        self.board_label.setFont(QFont("Courier", 22, QFont.Bold))
        self.board_label.setStyleSheet(
            "color: #E2E8F0; background-color: #111827; border: 3px solid #38BDF8; "
            "border-radius: 12px; padding: 18px 36px;"
        )
        self.board_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.board_label, alignment=Qt.AlignCenter)

        self.footer_label = QLabel("")
        self.footer_label.setFont(QFont("Courier", 18))
        self.footer_label.setStyleSheet("color: #94A3B8;")
        self.footer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.footer_label)

    def start_scoreboard(self, condition_name: str, score: int):
        self.condition_name = condition_name
        self.final_score = score
        self.letters = [0, 0, 0]
        self.slot_idx = 0

        self.title_label.setText(f"HIGH SCORES — {condition_name.upper()}")
        self.score_label.setText(f"YOUR SCORE: {score:04d}")
        self.prompt_label.setText(
            "ENTER YOUR INITIALS\n[LEFT / RIGHT ARROW] = Choose Letter   |   [UP ARROW] = Confirm Letter"
        )
        self.footer_label.setText("")
        self._update_slots_ui()
        self._render_leaderboard()
        self.setFocus()
        send_marker(f"Arcade_Scoreboard_Started_{condition_name}_Score_{score}")

    def _update_slots_ui(self):
        for i, lbl in enumerate(self.letter_labels):
            ch = self.alphabet[self.letters[i]]
            lbl.setText(ch)
            if i == self.slot_idx:
                lbl.setStyleSheet(
                    "color: #FACC15; background-color: #1E293B; "
                    "border: 4px solid #FACC15; border-radius: 12px;"
                )
            elif i < self.slot_idx:
                lbl.setStyleSheet(
                    "color: #2EC4B6; background-color: #0F172A; "
                    "border: 3px solid #2EC4B6; border-radius: 12px;"
                )
            else:
                lbl.setStyleSheet(
                    "color: #64748B; background-color: #0F172A; "
                    "border: 2px solid #334155; border-radius: 12px;"
                )

    def _scores_filepath(self):
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, f"arcade_scores_{self.condition_name}.json")

    def _load_scores(self):
        path = self._scores_filepath()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_current_score(self):
        initials = "".join(self.alphabet[idx] for idx in self.letters)
        scores = self._load_scores()
        scores.append({
            "name": initials,
            "score": self.final_score,
            "subject": state.subject_number,
            "time": time.strftime("%Y-%m-%d %H:%M")
        })
        scores.sort(key=lambda x: x["score"], reverse=True)
        scores = scores[:10]

        with open(self._scores_filepath(), "w", encoding="utf-8") as f:
            json.dump(scores, f, indent=2)

        send_marker(f"Arcade_Initials_Saved_{initials}_Score_{self.final_score}")
        self._render_leaderboard(scores)

    def _render_leaderboard(self, scores=None):
        if scores is None:
            scores = self._load_scores()
        if not scores:
            self.board_label.setText("NO SCORES RECORDED YET FOR THIS CONDITION")
            return

        lines = ["RANK   NAME    SCORE"]
        lines.append("------------------------")
        for idx, entry in enumerate(scores[:8], start=1):
            lines.append(f" #{idx:<4}  {entry['name']:<5}   {entry['score']:04d}")
        self.board_label.setText("\n".join(lines))

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return

        if self.slot_idx < 3:
            if event.key() == Qt.Key_Left:
                self.letters[self.slot_idx] = (self.letters[self.slot_idx] - 1) % 26
                self._update_slots_ui()
            elif event.key() == Qt.Key_Right:
                self.letters[self.slot_idx] = (self.letters[self.slot_idx] + 1) % 26
                self._update_slots_ui()
            elif event.key() in (Qt.Key_Up, Qt.Key_Return, Qt.Key_Enter):
                self.slot_idx += 1
                self._update_slots_ui()
                if self.slot_idx == 3:
                    self._save_current_score()
                    self.prompt_label.setText("SCORE SAVED!")
                    self.footer_label.setText("Press [UP ARROW] to return to Main Menu")
        else:
            if event.key() in (Qt.Key_Up, Qt.Key_Return, Qt.Key_Enter):
                self.finish_callback()
