import sys
import os
import json
import time
import random
import threading
import websocket
from PyQt5.QtCore import QRectF, QTimer, Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget
)
from PyQt5.QtMultimedia import QSoundEffect

# validation task parameters
HIT_POINTS = 5
WRONG_PENALTY = 5
TIME_TEST = 120  # task duration in seconds (120 = 2 minutes)

VALIDATION_LEADERBOARD_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "validation_leaderboard.txt"
)

# x16 motor group definitions (mapped across the 0-19 coordinate grid)
BACK_ALL = list(range(20))
BACK_LOWER = [4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19]
BACK_UPPER = [0, 1, 2, 3, 8, 9, 10, 11]
BACK_CENTER = [1, 2, 5, 6, 9, 10, 13, 14, 17, 18]
BACK_OUTER = [0, 3, 4, 7, 8, 11, 12, 15, 16, 19]

FRONT_ALL = list(range(20))
FRONT_LEFT = [0, 1, 4, 5, 8, 9, 12, 13, 16, 17]
FRONT_RIGHT = [2, 3, 6, 7, 10, 11, 14, 15, 18, 19]


def load_leaderboard():
    """reads validation leaderboard text file and returns entries sorted descending by score."""
    scores = []
    if os.path.exists(VALIDATION_LEADERBOARD_FILE):
        try:
            with open(VALIDATION_LEADERBOARD_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    parts = line.split(":")
                    if len(parts) >= 3:
                        name = parts[0].strip()
                        try:
                            sc = int(parts[1].strip())
                            err = float(parts[2].strip())
                            scores.append((name, sc, err))
                        except ValueError:
                            pass
        except Exception as e:
            print(f"error reading validation leaderboard file: {e}")
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def save_score(name, score, error_rate):
    """appends a score and error rate entry to the text file."""
    try:
        with open(VALIDATION_LEADERBOARD_FILE, "a", encoding="utf-8") as f:
            f.write(f"{name}:{score}:{error_rate:.1f}\n")
    except Exception as e:
        print(f"error writing score to validation leaderboard file: {e}")


def clear_leaderboard_file():
    """wipes the validation leaderboard text file."""
    try:
        with open(VALIDATION_LEADERBOARD_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        print(f"error clearing validation leaderboard file: {e}")


class FeedbackController:
    """manages persistent bhaptics player websocket connection, stimulus variants, spatial mapping, and audio playback."""

    def __init__(self, base_dir=".", pos_mode="positive_1", neg_mode="negative_1", mapping_mode="correct_back", audio_enabled=True):
        self.pos_mode = pos_mode
        self.neg_mode = neg_mode
        self.mapping_mode = mapping_mode
        self.audio_enabled = audio_enabled
        self._update_positions()

        self.ws_app = None
        self.connected = False
        self._start_bhaptics_client()

        # initialize low-latency wav players
        self.snd_correct = QSoundEffect()
        self.snd_incorrect = QSoundEffect()

        correct_path = os.path.join(base_dir, "audios/correct_answer.wav")
        incorrect_path = os.path.join(base_dir, "audios/incorrect_answer.wav")

        if os.path.exists(correct_path):
            self.snd_correct.setSource(QUrl.fromLocalFile(os.path.abspath(correct_path)))
            self.snd_correct.setVolume(0.9)

        if os.path.exists(incorrect_path):
            self.snd_incorrect.setSource(QUrl.fromLocalFile(os.path.abspath(incorrect_path)))
            self.snd_incorrect.setVolume(0.9)

    def set_modes(self, pos_mode, neg_mode, mapping_mode="correct_back", audio_enabled=True):
        self.pos_mode = pos_mode
        self.neg_mode = neg_mode
        self.mapping_mode = mapping_mode
        self.audio_enabled = audio_enabled
        self._update_positions()

    def _update_positions(self):
        if self.mapping_mode == "correct_front":
            self.pos_position = "VestFront"
            self.neg_position = "VestBack"
        else:  # default: correct_back
            self.pos_position = "VestBack"
            self.neg_position = "VestFront"

    def _start_bhaptics_client(self):
        url = "ws://127.0.0.1:15881/v2/feedbacks?app_id=assembly_x16&app_name=Cue_Validation_Task"

        def on_open(ws):
            self.connected = True

        def on_close(ws, close_status_code, close_msg):
            self.connected = False

        def on_error(ws, error):
            self.connected = False

        def on_message(ws, message):
            pass

        self.ws_app = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_close=on_close,
            on_error=on_error,
            on_message=on_message
        )

        def run_loop():
            while True:
                try:
                    self.ws_app.run_forever(ping_interval=5, ping_timeout=2)
                except Exception:
                    pass
                time.sleep(2.0)

        threading.Thread(target=run_loop, daemon=True).start()

    def _send_dot_frame(self, key, position, motor_tuples, duration_ms):
        if not self.connected or self.ws_app is None:
            return
        unique_key = f"{key}_{time.time_ns()}"
        dots = [{"index": int(idx), "intensity": int(val)} for idx, val in motor_tuples]
        payload = {
            "Submit": [
                {
                    "Type": "frame",
                    "Key": unique_key,
                    "Frame": {
                        "position": position,
                        "dotPoints": dots,
                        "durationMillis": int(duration_ms),
                        "pathPoints": []
                    }
                }
            ]
        }
        try:
            self.ws_app.send(json.dumps(payload))
        except Exception as e:
            print(f"bhaptics send error: {e}")

    def trigger_positive(self, mode_override=None):
        if self.audio_enabled and self.snd_correct.isLoaded():
            self.snd_correct.stop()
            self.snd_correct.play()
        mode = mode_override or self.pos_mode
        if mode == "random_all":
            mode = random.choice(["positive_1", "positive_2", "positive_3"])

        target_map = {
            "positive_1": self._pos_1_1p4hz,
            "positive_2": self._pos_2_upward_wave,
            "positive_3": self._pos_3_warm_swell
        }
        fn = target_map.get(mode, self._pos_1_1p4hz)
        threading.Thread(target=fn, daemon=True).start()
        return mode

    def trigger_negative(self, mode_override=None):
        if self.audio_enabled and self.snd_incorrect.isLoaded():
            self.snd_incorrect.stop()
            self.snd_incorrect.play()
        mode = mode_override or self.neg_mode
        if mode == "random_all":
            mode = random.choice(["negative_1", "negative_2", "negative_3"])

        target_map = {
            "negative_1": self._neg_1_0p5hz,
            "negative_2": self._neg_2_sharp_staccato,
            "negative_3": self._neg_3_chest_jitter
        }
        fn = target_map.get(mode, self._neg_1_0p5hz)
        threading.Thread(target=fn, daemon=True).start()
        return mode

    # ------------------------------------------------------------------ positive patterns (<= 500 ms)
    def _pos_1_1p4hz(self):
        pos = self.pos_position
        self._send_dot_frame("p1_a", pos, [(i, 35) for i in BACK_ALL], 60)
        time.sleep(0.05)
        self._send_dot_frame("p1_b", pos, [(i, 60) for i in BACK_ALL], 100)
        time.sleep(0.18)
        self._send_dot_frame("p1_c", pos, [(i, 35) for i in BACK_ALL], 60)
        time.sleep(0.05)
        self._send_dot_frame("p1_d", pos, [(i, 60) for i in BACK_ALL], 120)

    def _pos_2_upward_wave(self):
        pos = self.pos_position
        self._send_dot_frame("p2_low", pos, [(i, 35) for i in BACK_LOWER], 160)
        time.sleep(0.15)
        self._send_dot_frame("p2_mid", pos, [(i, 50) for i in BACK_ALL], 160)
        time.sleep(0.15)
        self._send_dot_frame("p2_high", pos, [(i, 65) for i in BACK_UPPER], 180)

    def _pos_3_warm_swell(self):
        pos = self.pos_position
        self._send_dot_frame("p3_1", pos, [(i, 25) for i in BACK_CENTER], 150)
        time.sleep(0.14)
        self._send_dot_frame("p3_2", pos, [(i, 55) for i in BACK_ALL], 200)
        time.sleep(0.14)
        self._send_dot_frame("p3_3", pos, [(i, 25) for i in BACK_OUTER], 200)

    # ------------------------------------------------------------------ negative patterns (<= 500 ms)
    def _neg_1_0p5hz(self):
        pos = self.neg_position
        self._send_dot_frame("n1_a", pos, [(i, 95) for i in FRONT_ALL], 240)
        time.sleep(0.24)
        self._send_dot_frame("n1_b", pos, [(i, 100) for i in FRONT_ALL], 240)

    def _neg_2_sharp_staccato(self):
        pos = self.neg_position
        front_max = [(i, 100) for i in FRONT_ALL]
        for step in range(3):
            duration = 120 if step == 2 else 100
            self._send_dot_frame(f"n2_{step}", pos, front_max, duration)
            if step < 2:
                time.sleep(0.18)

    def _neg_3_chest_jitter(self):
        pos = self.neg_position
        left_max = [(i, 100) for i in FRONT_LEFT]
        right_max = [(i, 100) for i in FRONT_RIGHT]
        for step in range(5):
            pattern = left_max if step % 2 == 0 else right_max
            self._send_dot_frame(f"n3_{step}", pos, pattern, 90)
            if step < 4:
                time.sleep(0.09)

    def close(self):
        if self.ws_app is not None:
            try:
                self.ws_app.close()
            except Exception:
                pass


class StimulusConfigDialog(QDialog):
    """startup selector allowing player name entry, spatial mapping, feedback modality, and cue preview."""

    def __init__(self, feedback_ctrl):
        super().__init__()
        self.feedback = feedback_ctrl
        self.setWindowTitle("Haptic Cue Validation Setup")
        self.setMinimumWidth(500)
        self.setStyleSheet("""
            QDialog { background-color: #0F172A; color: #F8FAFC; }
            QLabel { color: #E2E8F0; font-size: 14px; font-weight: bold; }
            QLineEdit {
                background-color: #1E293B; color: #F8FAFC; border: 1px solid #475569;
                border-radius: 6px; padding: 6px; font-size: 14px;
            }
            QComboBox {
                background-color: #1E293B; color: #F8FAFC; border: 1px solid #475569;
                border-radius: 6px; padding: 6px; font-size: 13px;
            }
            QPushButton {
                background-color: #334155; color: #F8FAFC; border: 1px solid #64748B;
                border-radius: 6px; padding: 7px 14px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #475569; }
            QPushButton#clearBtn {
                background-color: #991B1B; border-color: #EF4444; font-size: 12px;
            }
            QPushButton#clearBtn:hover { background-color: #7F1D1D; }
            QPushButton#startBtn {
                background-color: #16A34A; border-color: #22C55E; font-size: 15px; padding: 10px;
            }
            QPushButton#startBtn:hover { background-color: #15803D; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setSpacing(14)

        # player name field
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter subject / player name")
        self.name_input.setText("Player 1")
        form.addRow(QLabel("Participant Name:"), self.name_input)

        # feedback modality selector (Haptic + Audio vs. Haptics Only)
        self.modality_combo = QComboBox()
        self.modality_combo.addItem("Haptics + Audio", True)
        self.modality_combo.addItem("Haptics Only", False)
        form.addRow(QLabel("Feedback Modality:"), self.modality_combo)

        # spatial mapping selector
        self.map_combo = QComboBox()
        self.map_combo.addItem("Correct -> Back  |  Incorrect -> Front", "correct_back")
        self.map_combo.addItem("Correct -> Front |  Incorrect -> Back", "correct_front")
        self.map_combo.currentIndexChanged.connect(self._update_preview_labels)
        form.addRow(QLabel("Location Mapping:"), self.map_combo)

        # positive pattern selector
        pos_row = QHBoxLayout()
        self.pos_combo = QComboBox()
        self.pos_combo.addItem("Randomize All Positive Variants", "random_all")
        self.pos_combo.addItem("positive_1  (1.4 Hz Rhythmic Pulse)", "positive_1")
        self.pos_combo.addItem("positive_2  (Upward Spatial Wave)", "positive_2")
        self.pos_combo.addItem("positive_3  (Warm Gaussian Swell)", "positive_3")
        btn_test_pos = QPushButton("Test")
        btn_test_pos.clicked.connect(self._test_positive)
        pos_row.addWidget(self.pos_combo, stretch=1)
        pos_row.addWidget(btn_test_pos)
        self.lbl_pos = QLabel("Positive Pattern:")
        form.addRow(self.lbl_pos, pos_row)

        # negative pattern selector
        neg_row = QHBoxLayout()
        self.neg_combo = QComboBox()
        self.neg_combo.addItem("Randomize All Negative Variants", "random_all")
        self.neg_combo.addItem("negative_1  (0.5 Hz Heavy Thud)", "negative_1")
        self.neg_combo.addItem("negative_2  (4 Hz Sharp Staccato)", "negative_2")
        self.neg_combo.addItem("negative_3  (5 Hz Left/Right Jitter)", "negative_3")
        btn_test_neg = QPushButton("Test")
        btn_test_neg.clicked.connect(self._test_negative)
        neg_row.addWidget(self.neg_combo, stretch=1)
        neg_row.addWidget(btn_test_neg)
        self.lbl_neg = QLabel("Negative Pattern:")
        form.addRow(self.lbl_neg, neg_row)

        layout.addLayout(form)

        # clear leaderboard & start controls
        bottom_row = QHBoxLayout()
        btn_clear = QPushButton("Clear Leaderboard")
        btn_clear.setObjectName("clearBtn")
        btn_clear.clicked.connect(self._clear_leaderboard_action)
        bottom_row.addWidget(btn_clear)

        btn_start = QPushButton("Start Cue Validation Task")
        btn_start.setObjectName("startBtn")
        btn_start.clicked.connect(self.accept)
        bottom_row.addWidget(btn_start, stretch=1)

        layout.addLayout(bottom_row)
        self._update_preview_labels()

    def _update_preview_labels(self):
        mapping = self.map_combo.currentData()
        if mapping == "correct_front":
            self.lbl_pos.setText("Positive (Front):")
            self.lbl_neg.setText("Negative (Back):")
        else:
            self.lbl_pos.setText("Positive (Back):")
            self.lbl_neg.setText("Negative (Front):")

    def _test_positive(self):
        self.feedback.set_modes(
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData(),
            self.modality_combo.currentData()
        )
        self.feedback.trigger_positive()

    def _test_negative(self):
        self.feedback.set_modes(
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData(),
            self.modality_combo.currentData()
        )
        self.feedback.trigger_negative()

    def _clear_leaderboard_action(self):
        reply = QMessageBox.question(
            self, "Clear Leaderboard",
            "Are you sure you want to clear all validation leaderboard entries?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            clear_leaderboard_file()
            QMessageBox.information(self, "Leaderboard Cleared", "The validation leaderboard file has been cleared.")

    def get_selections(self):
        name = self.name_input.text().strip() or "Player 1"
        return (
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData(),
            self.modality_combo.currentData(),
            name
        )


class CueValidationGame(QWidget):
    """validation task testing perception accuracy of positive vs negative haptic cues."""

    def __init__(self, feedback_ctrl, player_name="Player 1"):
        super().__init__()
        self.feedback = feedback_ctrl
        self.player_name = player_name

        audio_str = "Audio ON" if self.feedback.audio_enabled else "Haptics Only"
        self.setWindowTitle(
            f"Haptic Cue Validation Task - bHaptics X16 [{audio_str}]"
        )
        self.setMinimumSize(840, 620)
        self.setFocusPolicy(Qt.StrongFocus)

        self.rng = random.Random()
        self.score = 0
        self.total_trials = 0
        self.correct_trials = 0
        self.incorrect_trials = 0
        self.error_rate = 0.0

        self.game_start_time = 0.0
        self.is_game_over = False
        self.score_saved = False
        self.leaderboard_data = []

        self.active_cue_type = None  # "positive" or "negative"
        self.active_pattern_mode = ""
        self.waiting_for_input = False
        self.last_result = None  # "CORRECT" or "INCORRECT"
        self.result_flash_time = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.start()

    def start(self):
        now = time.perf_counter()
        self.score = 0
        self.total_trials = 0
        self.correct_trials = 0
        self.incorrect_trials = 0
        self.error_rate = 0.0
        self.game_start_time = now
        self.is_game_over = False
        self.score_saved = False
        self._next_trial()
        self.timer.start(30)

    def _next_trial(self):
        """presents a new randomized haptic cue to the subject."""
        if self.is_game_over:
            return

        self.active_cue_type = self.rng.choice(["positive", "negative"])
        if self.active_cue_type == "positive":
            self.active_pattern_mode = self.feedback.trigger_positive()
        else:
            self.active_pattern_mode = self.feedback.trigger_negative()

        self.waiting_for_input = True
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if self.is_game_over or event.isAutoRepeat():
            return

        now = time.perf_counter()

        # replay current cue (Space or R)
        if event.key() in (Qt.Key_Space, Qt.Key_R):
            if self.waiting_for_input and self.active_cue_type:
                if self.active_cue_type == "positive":
                    self.feedback.trigger_positive(self.active_pattern_mode)
                else:
                    self.feedback.trigger_negative(self.active_pattern_mode)
            return

        # check answer selection: Left Arrow (Positive) vs Right Arrow (Negative)
        if self.waiting_for_input and event.key() in (Qt.Key_Left, Qt.Key_Right):
            user_guess = "positive" if event.key() == Qt.Key_Left else "negative"
            self.waiting_for_input = False
            self.total_trials += 1

            if user_guess == self.active_cue_type:
                self.score += HIT_POINTS
                self.correct_trials += 1
                self.last_result = "CORRECT"
            else:
                self.score -= WRONG_PENALTY
                self.incorrect_trials += 1
                self.last_result = "INCORRECT"

            self.error_rate = (self.incorrect_trials / self.total_trials) * 100.0
            self.result_flash_time = now
            self.update()

            # auto-advance to next trial after 750 ms feedback display
            QTimer.singleShot(750, self._next_trial)

    def _tick(self):
        now = time.perf_counter()
        if now - self.game_start_time >= TIME_TEST:
            if not self.is_game_over:
                self.is_game_over = True
                self.timer.stop()
                if not self.score_saved:
                    save_score(self.player_name, self.score, self.error_rate)
                    self.score_saved = True
                self.leaderboard_data = load_leaderboard()
            self.update()
            return
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        now = time.perf_counter()

        # background gradient
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, QColor("#0B1220"))
        bg.setColorAt(1, QColor("#111A2E"))
        painter.fillRect(0, 0, w, h, QBrush(bg))

        # top hud bar
        hud = QRectF(16, 16, w - 32, 56)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 220))
        painter.drawRoundedRect(hud, 10, 10)
        painter.setFont(QFont("Helvetica", 15, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(
            hud.adjusted(16, 0, -16, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"SCORE: {self.score:04d}   |   TRIALS: {self.total_trials}"
        )

        # status readout center
        vest_status = "VEST: OK" if self.feedback.connected else "VEST: DISCONNECTED"
        audio_status = "+AUDIO" if self.feedback.audio_enabled else "NO AUDIO"
        mode_label = f"{vest_status}   ({audio_status})   |   ERROR RATE: {self.error_rate:.1f}%"
        painter.setFont(QFont("Helvetica", 10, QFont.Bold))
        painter.setPen(QColor("#4ADE80") if self.feedback.connected else QColor("#F87171"))
        painter.drawText(hud, Qt.AlignCenter, mode_label)

        remaining = max(0, TIME_TEST - (now - self.game_start_time if not self.is_game_over else TIME_TEST))
        mins, secs = divmod(int(remaining), 60)
        time_str = f"{mins:02d}:{secs:02d}"

        painter.setFont(QFont("Helvetica", 15, QFont.Bold))
        painter.setPen(QColor("#38BDF8"))
        painter.drawText(
            hud.adjusted(16, 0, -16, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            f"TIME: {time_str}"
        )

        # main stimulus instruction / result feedback banner
        srect = QRectF(w * 0.08, 90, w * 0.84, 52)
        if not self.waiting_for_input and self.last_result:
            if self.last_result == "CORRECT":
                painter.setPen(QPen(QColor("#22C55E"), 2))
                painter.setBrush(QColor(20, 83, 45, 230))
                painter.drawRoundedRect(srect, 10, 10)
                painter.setFont(QFont("Helvetica", 15, QFont.Black))
                painter.setPen(QColor("#4ADE80"))
                painter.drawText(srect, Qt.AlignCenter, "CORRECT IDENTIFICATION (+5 PTS)")
            else:
                painter.setPen(QPen(QColor("#EF4444"), 2))
                painter.setBrush(QColor(127, 29, 29, 230))
                painter.drawRoundedRect(srect, 10, 10)
                painter.setFont(QFont("Helvetica", 15, QFont.Black))
                painter.setPen(QColor("#FCA5A5"))
                painter.drawText(srect, Qt.AlignCenter, "INCORRECT / MISIDENTIFIED (-5 PTS)")
        else:
            painter.setPen(QPen(QColor("#38BDF8"), 2))
            painter.setBrush(QColor(30, 41, 59, 200))
            painter.drawRoundedRect(srect, 10, 10)
            painter.setFont(QFont("Helvetica", 13, QFont.Bold))
            painter.setPen(QColor("#F8FAFC"))
            painter.drawText(srect, Qt.AlignCenter, "CUE DELIVERED — CLASSIFY CUE TYPE NOW")

        # 2 large response classification cards (Left = Positive, Right = Negative)
        card_w = (w * 0.84 - 24) / 2
        card_h = h - 230
        cy = 160

        # Left Card (Positive / Correct Cue)
        left_rect = QRectF(w * 0.08, cy, card_w, card_h)
        painter.setPen(QPen(QColor("#22C55E"), 3 if self.waiting_for_input else 2))
        painter.setBrush(QColor(20, 83, 45, 120))
        painter.drawRoundedRect(left_rect, 14, 14)

        painter.setFont(QFont("Helvetica", 28, QFont.Black))
        painter.setPen(QColor("#4ADE80"))
        painter.drawText(QRectF(left_rect.x(), left_rect.y() + 30, left_rect.width(), 45), Qt.AlignCenter, "←  LEFT ARROW")

        painter.setFont(QFont("Helvetica", 18, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(QRectF(left_rect.x(), left_rect.y() + 85, left_rect.width(), 35), Qt.AlignCenter, "POSITIVE / CORRECT")

        painter.setFont(QFont("Helvetica", 11, QFont.Normal))
        painter.setPen(QColor("#86EFAC"))
        painter.drawText(
            QRectF(left_rect.x() + 16, left_rect.y() + 130, left_rect.width() - 32, 60),
            Qt.AlignCenter | Qt.TextWordWrap,
            "Press Left Arrow if you perceived a Positive / Correct haptic pattern."
        )

        # Right Card (Negative / Incorrect Cue)
        right_rect = QRectF(w * 0.08 + card_w + 24, cy, card_w, card_h)
        painter.setPen(QPen(QColor("#EF4444"), 3 if self.waiting_for_input else 2))
        painter.setBrush(QColor(127, 29, 29, 120))
        painter.drawRoundedRect(right_rect, 14, 14)

        painter.setFont(QFont("Helvetica", 28, QFont.Black))
        painter.setPen(QColor("#F87171"))
        painter.drawText(QRectF(right_rect.x(), right_rect.y() + 30, right_rect.width(), 45), Qt.AlignCenter, "RIGHT ARROW  →")

        painter.setFont(QFont("Helvetica", 18, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(QRectF(right_rect.x(), right_rect.y() + 85, right_rect.width(), 35), Qt.AlignCenter, "NEGATIVE / INCORRECT")

        painter.setFont(QFont("Helvetica", 11, QFont.Normal))
        painter.setPen(QColor("#FCA5A5"))
        painter.drawText(
            QRectF(right_rect.x() + 16, right_rect.y() + 130, right_rect.width() - 32, 60),
            Qt.AlignCenter | Qt.TextWordWrap,
            "Press Right Arrow if you perceived a Negative / Incorrect haptic pattern."
        )

        # bottom controls bar
        footer_y = h - 58
        ctrl_rect = QRectF(w * 0.08, footer_y, w * 0.84, 44)
        painter.setPen(QPen(QColor("#475569"), 2))
        painter.setBrush(QColor("#1E293B"))
        painter.drawRoundedRect(ctrl_rect, 10, 10)

        painter.setFont(QFont("Helvetica", 11, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(
            ctrl_rect,
            Qt.AlignCenter,
            "CONTROLS:  [← Left] Positive Cue   |   [→ Right] Negative Cue   |   [SPACE / R] Replay Cue   |   [ESC] Exit"
        )

        # game over & leaderboard overlay
        if self.is_game_over:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 23, 42, 248))
            painter.drawRect(0, 0, int(w), int(h))

            painter.setPen(QColor("#F8FAFC"))
            painter.setFont(QFont("Helvetica", 30, QFont.Black))
            painter.drawText(QRectF(0, h * 0.06, w, 44), Qt.AlignCenter, "VALIDATION SESSION COMPLETE!")

            painter.setPen(QColor("#4ADE80"))
            painter.setFont(QFont("Helvetica", 18, QFont.Bold))
            painter.drawText(
                QRectF(0, h * 0.14, w, 32),
                Qt.AlignCenter,
                f"{self.player_name}  —  Score: {self.score} pts   |   Error Rate: {self.error_rate:.1f}% ({self.total_trials} Trials)"
            )

            # leaderboard box
            lb_rect = QRectF(w * 0.15, h * 0.22, w * 0.70, h * 0.60)
            painter.setPen(QPen(QColor("#334155"), 2))
            painter.setBrush(QColor(30, 41, 59, 235))
            painter.drawRoundedRect(lb_rect, 14, 14)

            painter.setPen(QColor("#38BDF8"))
            painter.setFont(QFont("Helvetica", 18, QFont.Bold))
            painter.drawText(QRectF(lb_rect.x(), lb_rect.y() + 15, lb_rect.width(), 30), Qt.AlignCenter, "VALIDATION LEADERBOARD")

            top_scores = self.leaderboard_data[:5]
            y_offset = lb_rect.y() + 58
            painter.setFont(QFont("Helvetica", 13, QFont.Normal))

            for i, (name, sc, err) in enumerate(top_scores):
                rank_str = f"#{i+1}   {name}"
                score_str = f"{sc:04d} pts   (Error Rate: {err:.1f}%)"

                is_current = (name == self.player_name and sc == self.score)
                painter.setPen(QColor("#F5C518") if is_current else QColor("#E2E8F0"))

                row_rect = QRectF(lb_rect.x() + 30, y_offset, lb_rect.width() - 60, 28)
                painter.drawText(row_rect, Qt.AlignLeft | Qt.AlignVCenter, rank_str)
                painter.drawText(row_rect, Qt.AlignRight | Qt.AlignVCenter, score_str)
                y_offset += 32

            painter.setPen(QColor("#94A3B8"))
            painter.setFont(QFont("Helvetica", 12, QFont.Bold))
            painter.drawText(QRectF(0, h * 0.86, w, 32), Qt.AlignCenter, "Press ESC to Exit")

    def closeEvent(self, event):
        self.timer.stop()
        self.feedback.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    feedback = FeedbackController(base_dir=base_dir)

    dialog = StimulusConfigDialog(feedback)
    if dialog.exec_() == QDialog.Accepted:
        pos_choice, neg_choice, map_choice, audio_choice, player_name = dialog.get_selections()
        feedback.set_modes(pos_choice, neg_choice, map_choice, audio_choice)
        window = CueValidationGame(feedback, player_name=player_name)
        window.show()
        sys.exit(app.exec_())
    else:
        feedback.close()
        sys.exit(0)