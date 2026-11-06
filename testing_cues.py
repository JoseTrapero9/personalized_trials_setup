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

# game parameters
STEP_HIT_POINTS = 10
UNIT_BONUS_POINTS = 20
STEP_WRONG_PENALTY = 5
TIME_TEST = 120  # game duration in seconds (120 = 2 minutes)
AUDIO_GONE_IN = 30  # duration in seconds after which audio cues disappear

STEPS_INFO = [
    ("STEP 1: BASE ALIGNMENT", ["PORT A", "PORT B", "PORT C"]),
    ("STEP 2: CORE INSERTION", ["CELL X", "CELL Y", "CELL Z"]),
    ("STEP 3: CONDUIT ROUTING", ["LINE 1", "LINE 2", "LINE 3"]),
    ("STEP 4: SEAL LOCKING", ["LOCK L", "LOCK C", "LOCK R"])
]
KEY_GLYPHS = ["←", "↑", "→"]

LEADERBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaderboard.txt")

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
    """reads leaderboard text file and returns entries sorted descending by score."""
    scores = []
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    parts = line.rsplit(":", 1)
                    name = parts[0].strip()
                    try:
                        score = int(parts[1].strip())
                        scores.append((name, score))
                    except ValueError:
                        pass
        except Exception as e:
            print(f"error reading leaderboard file: {e}")
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def save_score(name, score):
    """appends a score entry to the text file."""
    try:
        with open(LEADERBOARD_FILE, "a", encoding="utf-8") as f:
            f.write(f"{name}: {score}\n")
    except Exception as e:
        print(f"error writing score to leaderboard file: {e}")


def clear_leaderboard_file():
    """wipes the leaderboard text file."""
    try:
        with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        print(f"error clearing leaderboard file: {e}")


class FeedbackController:
    """manages persistent bhaptics player websocket connection, stimulus variants, spatial mapping, audio toggling, and wav playback."""

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
        else:
            print(f"warning: audio file not found at {correct_path}")

        if os.path.exists(incorrect_path):
            self.snd_incorrect.setSource(QUrl.fromLocalFile(os.path.abspath(incorrect_path)))
            self.snd_incorrect.setVolume(0.9)
        else:
            print(f"warning: audio file not found at {incorrect_path}")

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
        url = "ws://127.0.0.1:15881/v2/feedbacks?app_id=assembly_x16&app_name=Procedural_Assembly_Game"

        def on_open(ws):
            self.connected = True
            print("connected to bhaptics player.")

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

    def trigger_correct(self, mode_override=None):
        if self.audio_enabled and self.snd_correct.isLoaded():
            self.snd_correct.stop()
            self.snd_correct.play()
        mode = mode_override or self.pos_mode
        target_map = {
            "positive_1": self._pos_1_1p4hz,
            "positive_2": self._pos_2_upward_wave,
            "positive_3": self._pos_3_warm_swell
        }
        fn = target_map.get(mode, self._pos_1_1p4hz)
        threading.Thread(target=fn, daemon=True).start()

    def trigger_incorrect(self, mode_override=None):
        if self.audio_enabled and self.snd_incorrect.isLoaded():
            self.snd_incorrect.stop()
            self.snd_incorrect.play()
        mode = mode_override or self.neg_mode
        target_map = {
            "negative_1": self._neg_1_0p5hz,
            "negative_2": self._neg_2_sharp_staccato,
            "negative_3": self._neg_3_chest_jitter
        }
        fn = target_map.get(mode, self._neg_1_0p5hz)
        threading.Thread(target=fn, daemon=True).start()

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
    """startup selector allowing player name entry, haptic spatial mapping, audio modality, and haptic conditions preview."""

    def __init__(self, feedback_ctrl):
        super().__init__()
        self.feedback = feedback_ctrl
        self.setWindowTitle("Select Haptic Stimulus Conditions")
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
        self.name_input.setPlaceholderText("Enter your name")
        self.name_input.setText("Player 1")
        form.addRow(QLabel("Player Name:"), self.name_input)

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

        # positive selector + preview button
        pos_row = QHBoxLayout()
        self.pos_combo = QComboBox()
        self.pos_combo.addItem("positive_1  (1.4 Hz Rhythmic Pulse)", "positive_1")
        self.pos_combo.addItem("positive_2  (Upward Spatial Wave)", "positive_2")
        self.pos_combo.addItem("positive_3  (Warm Gaussian Swell)", "positive_3")
        btn_test_pos = QPushButton("Test")
        btn_test_pos.clicked.connect(self._test_positive)
        pos_row.addWidget(self.pos_combo, stretch=1)
        pos_row.addWidget(btn_test_pos)
        self.lbl_pos = QLabel("Correct Cue:")
        form.addRow(self.lbl_pos, pos_row)

        # negative selector + preview button
        neg_row = QHBoxLayout()
        self.neg_combo = QComboBox()
        self.neg_combo.addItem("negative_1  (0.5 Hz Heavy Thud)", "negative_1")
        self.neg_combo.addItem("negative_2  (4 Hz Sharp Staccato)", "negative_2")
        self.neg_combo.addItem("negative_3  (5 Hz Left/Right Jitter)", "negative_3")
        btn_test_neg = QPushButton("Test")
        btn_test_neg.clicked.connect(self._test_negative)
        neg_row.addWidget(self.neg_combo, stretch=1)
        neg_row.addWidget(btn_test_neg)
        self.lbl_neg = QLabel("Incorrect Cue:")
        form.addRow(self.lbl_neg, neg_row)

        layout.addLayout(form)

        # clear leaderboard & start controls
        bottom_row = QHBoxLayout()
        btn_clear = QPushButton("Clear Leaderboard")
        btn_clear.setObjectName("clearBtn")
        btn_clear.clicked.connect(self._clear_leaderboard_action)
        bottom_row.addWidget(btn_clear)

        btn_start = QPushButton("Start Assembly Task")
        btn_start.setObjectName("startBtn")
        btn_start.clicked.connect(self.accept)
        bottom_row.addWidget(btn_start, stretch=1)

        layout.addLayout(bottom_row)
        self._update_preview_labels()

    def _update_preview_labels(self):
        mapping = self.map_combo.currentData()
        if mapping == "correct_front":
            self.lbl_pos.setText("Correct (Front):")
            self.lbl_neg.setText("Incorrect (Back):")
        else:
            self.lbl_pos.setText("Correct (Back):")
            self.lbl_neg.setText("Incorrect (Front):")

    def _test_positive(self):
        self.feedback.set_modes(
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData(),
            self.modality_combo.currentData()
        )
        self.feedback.trigger_correct()

    def _test_negative(self):
        self.feedback.set_modes(
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData(),
            self.modality_combo.currentData()
        )
        self.feedback.trigger_incorrect()

    def _clear_leaderboard_action(self):
        reply = QMessageBox.question(
            self, "Clear Leaderboard",
            "Are you sure you want to clear all leaderboard entries?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            clear_leaderboard_file()
            QMessageBox.information(self, "Leaderboard Cleared", "The leaderboard text file has been cleared.")

    def get_selections(self):
        name = self.name_input.text().strip() or "Player 1"
        return (
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData(),
            self.modality_combo.currentData(),
            name
        )


class ProceduralAssemblyGame(QWidget):
    """manual-progression assembly where rejected units remain frozen until user advances to a new unit."""

    def __init__(self, feedback_ctrl, player_name="Player 1"):
        super().__init__()
        self.feedback = feedback_ctrl
        self.player_name = player_name
        self.initial_audio_enabled = self.feedback.audio_enabled

        audio_str = "Audio ON" if self.feedback.audio_enabled else "Haptics Only"
        self.setWindowTitle(
            f"Procedural Assembly - bHaptics X16 [{self.feedback.pos_mode} | {self.feedback.neg_mode} | Map: {self.feedback.mapping_mode} | {audio_str}]"
        )
        self.setMinimumSize(840, 620)
        self.setFocusPolicy(Qt.StrongFocus)

        self.rng = random.Random()
        self.visible_score = 0
        self.pending_score = 0
        self.units_completed = 0
        self.game_start_time = 0.0
        self.is_game_over = False
        self.score_saved = False
        self.leaderboard_data = []

        # assembly state variables
        self.target_sequence = []
        self.current_step = 0
        self.installed_choices = [None, None, None, None]
        self.step_awarded = [False, False, False, False]
        self.unit_submitted = False
        self.reveal_success = False

        self.undo_flash = 0.0
        self.advance_flash = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.start()

    def start(self):
        now = time.perf_counter()
        self.visible_score = 0
        self.pending_score = 0
        self.units_completed = 0
        self.game_start_time = now
        self.is_game_over = False
        self.score_saved = False
        self.feedback.audio_enabled = self.initial_audio_enabled
        self._new_unit()
        self.timer.start(30)

    def _new_unit(self):
        """generates a brand-new hidden 4-step assembly configuration."""
        self.target_sequence = [self.rng.randrange(3) for _ in range(4)]
        self.current_step = 0
        self.installed_choices = [None, None, None, None]
        self.step_awarded = [False, False, False, False]
        self.unit_submitted = False
        self.reveal_success = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if self.is_game_over or event.isAutoRepeat():
            return

        now = time.perf_counter()

        # manual extract / undo on the current step (E key)
        if event.key() == Qt.Key_E:
            if not self.unit_submitted:
                self._undo_step(now)
            return

        # manual advance to next step, submit unit, or move from rejected unit to a new unit
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if self.unit_submitted:
                self._new_unit()
            else:
                self._manual_advance(now)
            return

        # seat a component option on the current step
        if not self.unit_submitted:
            if event.key() == Qt.Key_Left:
                self._seat_component(0)
            elif event.key() == Qt.Key_Up:
                self._seat_component(1)
            elif event.key() == Qt.Key_Right:
                self._seat_component(2)

    def _undo_step(self, now):
        """extracts the currently seated component on the active step so the user can select another."""
        if self.installed_choices[self.current_step] is not None:
            self.installed_choices[self.current_step] = None
            self.undo_flash = now
            self.update()

    def _seat_component(self, choice_idx):
        """seats a part on the active step and delivers haptic/audio feedback without advancing."""
        if self.installed_choices[self.current_step] is not None:
            self.feedback.trigger_incorrect()
            return

        self.installed_choices[self.current_step] = choice_idx
        target = self.target_sequence[self.current_step]

        if choice_idx == target:
            if not self.step_awarded[self.current_step]:
                self.pending_score += STEP_HIT_POINTS
                self.step_awarded[self.current_step] = True
            self.feedback.trigger_correct()
        else:
            self.pending_score -= STEP_WRONG_PENALTY
            if self.visible_score + self.pending_score < 0:
                self.pending_score = -self.visible_score
            self.feedback.trigger_incorrect()

        self.update()

    def _manual_advance(self, now):
        """manually moves to the next step (or evaluates the full unit after step 4)."""
        if self.installed_choices[self.current_step] is None:
            self.feedback.trigger_incorrect()
            return

        self.advance_flash = now

        if self.current_step < 3:
            self.current_step += 1
        else:
            self.unit_submitted = True
            all_correct = all(
                self.installed_choices[i] == self.target_sequence[i]
                for i in range(4)
            )
            if all_correct:
                self.units_completed += 1
                self.pending_score += UNIT_BONUS_POINTS
                self.visible_score = max(0, self.visible_score + self.pending_score)
                self.pending_score = 0
                self.reveal_success = True
            else:
                self.pending_score -= STEP_WRONG_PENALTY
                self.visible_score = max(0, self.visible_score + self.pending_score)
                self.pending_score = 0
                self.reveal_success = False
                self.feedback.trigger_incorrect()

        self.update()

    def _tick(self):
        now = time.perf_counter()
        elapsed = now - self.game_start_time

        # mute audio after AUDIO_GONE_IN seconds if initially enabled
        if self.initial_audio_enabled:
            self.feedback.audio_enabled = (elapsed < AUDIO_GONE_IN)

        if elapsed >= TIME_TEST:
            if not self.is_game_over:
                self.is_game_over = True
                self.timer.stop()
                final_score = max(0, self.visible_score + self.pending_score)
                self.visible_score = final_score
                self.pending_score = 0
                if not self.score_saved:
                    save_score(self.player_name, self.visible_score)
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

        # outer border highlight if unit is submitted
        if self.unit_submitted:
            border_c = QColor("#22C55E") if self.reveal_success else QColor("#EF4444")
            painter.setPen(QPen(border_c, 6))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(4, 4, w - 8, h - 8), 14, 14)

        # top hud bar
        hud = QRectF(16, 16, w - 32, 56)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 220))
        painter.drawRoundedRect(hud, 10, 10)
        painter.setFont(QFont("Helvetica", 16, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(
            hud.adjusted(16, 0, -16, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"SCORE: {self.visible_score:04d}   |   UNITS: {self.units_completed}"
        )

        vest_status = "VEST: OK" if self.feedback.connected else "VEST: DISCONNECTED"
        pos_loc = "FRONT" if self.feedback.pos_position == "VestFront" else "BACK"
        neg_loc = "FRONT" if self.feedback.neg_position == "VestFront" else "BACK"
        snd_label = "+AUDIO" if self.feedback.audio_enabled else "NO AUDIO"
        mode_label = f"{vest_status}  (+{pos_loc} | -{neg_loc} | {snd_label})"
        painter.setFont(QFont("Helvetica", 10, QFont.Bold))
        painter.setPen(QColor("#4ADE80") if self.feedback.connected else QColor("#F87171"))
        painter.drawText(hud, Qt.AlignCenter, mode_label)

        remaining = max(0, TIME_TEST - (now - self.game_start_time if not self.is_game_over else TIME_TEST))
        mins, secs = divmod(int(remaining), 60)
        time_str = f"{mins:02d}:{secs:02d}"

        painter.setFont(QFont("Helvetica", 16, QFont.Bold))
        painter.setPen(QColor("#38BDF8"))
        painter.drawText(
            hud.adjusted(16, 0, -16, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            f"TIME: {time_str}"
        )

        # instruction / submission status banner
        srect = QRectF(w * 0.06, 84, w * 0.88, 44)
        if self.unit_submitted:
            if self.reveal_success:
                painter.setPen(QPen(QColor("#22C55E"), 2))
                painter.setBrush(QColor(20, 83, 45, 210))
                painter.drawRoundedRect(srect, 10, 10)
                painter.setFont(QFont("Helvetica", 13, QFont.Black))
                painter.setPen(QColor("#4ADE80"))
                painter.drawText(srect, Qt.AlignCenter, "UNIT VERIFIED!  [PRESS SPACE TO START NEW UNIT]")
            else:
                painter.setPen(QPen(QColor("#EF4444"), 2))
                painter.setBrush(QColor(127, 29, 29, 210))
                painter.drawRoundedRect(srect, 10, 10)
                painter.setFont(QFont("Helvetica", 13, QFont.Black))
                painter.setPen(QColor("#FCA5A5"))
                painter.drawText(srect, Qt.AlignCenter, "UNIT REJECTED (FAULTS FOUND)!  [PRESS SPACE TO WORK ON NEW UNIT]")
        else:
            painter.setPen(QPen(QColor("#475569"), 2))
            painter.setBrush(QColor(30, 41, 59, 180))
            painter.drawRoundedRect(srect, 10, 10)
            painter.setFont(QFont("Helvetica", 11, QFont.Bold))
            painter.setPen(QColor("#E2E8F0"))
            painter.drawText(
                srect,
                Qt.AlignCenter,
                f"{pos_loc} PULSE = CORRECT (SPACE = NEXT STEP)  |  {neg_loc} BUZZ = FAULT (E = EXTRACT)"
            )

        # 4 assembly step rows
        top_start = srect.bottom() + 18
        available_h = h - top_start - 95
        row_gap = 12
        row_h = (available_h - 3 * row_gap) / 4

        for step_idx, (step_title, options) in enumerate(STEPS_INFO):
            ry = top_start + step_idx * (row_h + row_gap)
            row_rect = QRectF(w * 0.06, ry, w * 0.88, row_h)

            has_part = (self.installed_choices[step_idx] is not None)
            is_active = (step_idx == self.current_step) and not self.unit_submitted
            step_is_correct = (self.installed_choices[step_idx] == self.target_sequence[step_idx])

            if self.unit_submitted:
                if step_is_correct:
                    border_col = QColor("#22C55E")
                    bg_col = QColor(20, 83, 45, 110)
                    status_str = "VERIFIED CORRECT"
                    status_col = QColor("#4ADE80")
                else:
                    border_col = QColor("#EF4444")
                    bg_col = QColor(127, 29, 29, 110)
                    status_str = "FAULT DETECTED"
                    status_col = QColor("#F87171")
            elif is_active:
                border_col = QColor("#38BDF8")
                bg_col = QColor(30, 41, 59, 225)
                if has_part:
                    status_str = "PART SEATED (E EXTRACT  |  SPACE NEXT)"
                    status_col = QColor("#E2E8F0")
                else:
                    status_str = "ACTIVE STEP: SELECT [← / ↑ / →]"
                    status_col = QColor("#38BDF8")
            else:
                border_col = QColor("#475569") if has_part else QColor("#334155")
                bg_col = QColor(30, 41, 59, 150) if has_part else QColor(15, 23, 42, 130)
                status_str = "PART SEATED" if has_part else "PENDING"
                status_col = QColor("#94A3B8") if has_part else QColor("#64748B")

            painter.setPen(QPen(border_col, 3 if is_active else 2))
            painter.setBrush(bg_col)
            painter.drawRoundedRect(row_rect, 12, 12)

            # left label column inside step row
            title_rect = QRectF(row_rect.x() + 18, row_rect.y() + 10, row_rect.width() * 0.38, row_rect.height() - 20)
            painter.setFont(QFont("Helvetica", 13, QFont.Bold))
            painter.setPen(QColor("#F8FAFC") if (is_active or has_part or self.unit_submitted) else QColor("#64748B"))
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, step_title)

            painter.setFont(QFont("Helvetica", 10, QFont.Bold))
            painter.setPen(status_col)
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignBottom, status_str)

            # 3 component option slots on the right side of the row
            opt_area_x = row_rect.x() + row_rect.width() * 0.41
            opt_area_w = row_rect.width() * 0.57
            opt_gap = 12
            opt_w = (opt_area_w - 2 * opt_gap) / 3
            opt_h = row_rect.height() - 20
            opt_y = row_rect.y() + 10

            for opt_idx, opt_label in enumerate(options):
                ox = opt_area_x + opt_idx * (opt_w + opt_gap)
                orect = QRectF(ox, opt_y, opt_w, opt_h)

                chosen_here = (self.installed_choices[step_idx] == opt_idx)

                if self.unit_submitted and chosen_here:
                    if step_is_correct:
                        oborder = QColor("#22C55E")
                        obg = QColor("#15803D")
                        otext_col = QColor("#FFFFFF")
                    else:
                        oborder = QColor("#EF4444")
                        obg = QColor("#991B1B")
                        otext_col = QColor("#FEE2E2")
                elif chosen_here:
                    oborder = QColor("#38BDF8")
                    obg = QColor("#1E3A8A")
                    otext_col = QColor("#F8FAFC")
                elif is_active:
                    oborder = QColor("#64748B")
                    obg = QColor("#1E293B")
                    otext_col = QColor("#E2E8F0")
                else:
                    oborder = QColor("#334155")
                    obg = QColor("#0F172A")
                    otext_col = QColor("#64748B")

                painter.setPen(QPen(oborder, 2))
                painter.setBrush(obg)
                painter.drawRoundedRect(orect, 8, 8)

                painter.setFont(QFont("Helvetica", 12, QFont.Bold))
                painter.setPen(otext_col)
                label_with_key = f"{KEY_GLYPHS[opt_idx]}  {opt_label}"
                painter.drawText(orect, Qt.AlignCenter, label_with_key)

        # bottom controls bar
        footer_y = h - 68
        ctrl_rect = QRectF(w * 0.06, footer_y, w * 0.88, 50)
        act_flash = (now - self.undo_flash < 0.18) or (now - self.advance_flash < 0.18)
        painter.setPen(QPen(QColor("#38BDF8") if act_flash else QColor("#475569"), 2))
        painter.setBrush(QColor("#334155") if act_flash else QColor("#1E293B"))
        painter.drawRoundedRect(ctrl_rect, 10, 10)

        painter.setFont(QFont("Helvetica", 12, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(
            ctrl_rect,
            Qt.AlignCenter,
            "CONTROLS:  [← / ↑ / →] Seat Part   |   [E] Extract Part   |   [SPACE / ENTER] Next Step / New Unit"
        )

        # game over & leaderboard overlay
        if self.is_game_over:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 23, 42, 245))
            painter.drawRect(0, 0, int(w), int(h))

            painter.setPen(QColor("#F8FAFC"))
            painter.setFont(QFont("Helvetica", 32, QFont.Black))
            painter.drawText(QRectF(0, h * 0.07, w, 46), Qt.AlignCenter, "SHIFT COMPLETE!")

            painter.setPen(QColor("#4ADE80"))
            painter.setFont(QFont("Helvetica", 20, QFont.Bold))
            painter.drawText(
                QRectF(0, h * 0.15, w, 36),
                Qt.AlignCenter,
                f"{self.player_name}'s Score: {self.visible_score:04d}   ({self.units_completed} Units Built)"
            )

            # leaderboard box
            lb_rect = QRectF(w * 0.18, h * 0.24, w * 0.64, h * 0.58)
            painter.setPen(QPen(QColor("#334155"), 2))
            painter.setBrush(QColor(30, 41, 59, 230))
            painter.drawRoundedRect(lb_rect, 14, 14)

            painter.setPen(QColor("#38BDF8"))
            painter.setFont(QFont("Helvetica", 18, QFont.Bold))
            painter.drawText(QRectF(lb_rect.x(), lb_rect.y() + 15, lb_rect.width(), 30), Qt.AlignCenter, "LEADERBOARD")

            # top 5 entries
            top_scores = self.leaderboard_data[:5]
            y_offset = lb_rect.y() + 60
            painter.setFont(QFont("Helvetica", 14, QFont.Normal))

            for i, (name, sc) in enumerate(top_scores):
                rank_str = f"#{i+1}   {name}"
                score_str = f"{sc:04d} pts"

                is_current = (name == self.player_name and sc == self.visible_score)
                painter.setPen(QColor("#F5C518") if is_current else QColor("#E2E8F0"))

                row_rect = QRectF(lb_rect.x() + 30, y_offset, lb_rect.width() - 60, 30)
                painter.drawText(row_rect, Qt.AlignLeft | Qt.AlignVCenter, rank_str)
                painter.drawText(row_rect, Qt.AlignRight | Qt.AlignVCenter, score_str)
                y_offset += 34

            painter.setPen(QColor("#94A3B8"))
            painter.setFont(QFont("Helvetica", 13, QFont.Bold))
            painter.drawText(QRectF(0, h * 0.86, w, 36), Qt.AlignCenter, "Press ESC to Exit")

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
        window = ProceduralAssemblyGame(feedback, player_name=player_name)
        window.show()
        sys.exit(app.exec_())
    else:
        feedback.close()
        sys.exit(0)