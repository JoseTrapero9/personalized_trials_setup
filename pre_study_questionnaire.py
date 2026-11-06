import sys
import os
import json
import time
from datetime import datetime
import threading
import websocket
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSlider, QVBoxLayout, QWidget
)

# Output directory for saved responses
ANSWERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "answers pre study")

# x16 motor group definitions (mapped across the 0-19 coordinate grid)
BACK_ALL = list(range(20))
BACK_LOWER = [4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19]
BACK_UPPER = [0, 1, 2, 3, 8, 9, 10, 11]
BACK_CENTER = [1, 2, 5, 6, 9, 10, 13, 14, 17, 18]
BACK_OUTER = [0, 3, 4, 7, 8, 11, 12, 15, 16, 19]

FRONT_ALL = list(range(20))
FRONT_LEFT = [0, 1, 4, 5, 8, 9, 12, 13, 16, 17]
FRONT_RIGHT = [2, 3, 6, 7, 10, 11, 14, 15, 18, 19]


class FeedbackController:
    """manages persistent bhaptics player websocket connection and stimulus variants."""

    def __init__(self, pos_mode="positive_1", neg_mode="negative_1", mapping_mode="correct_back"):
        self.pos_mode = pos_mode
        self.neg_mode = neg_mode
        self.mapping_mode = mapping_mode
        self._update_positions()

        self.ws_app = None
        self.connected = False
        self._start_bhaptics_client()

    def set_modes(self, pos_mode, neg_mode, mapping_mode="correct_back"):
        self.pos_mode = pos_mode
        self.neg_mode = neg_mode
        self.mapping_mode = mapping_mode
        self._update_positions()

    def _update_positions(self):
        if self.mapping_mode == "correct_front":
            self.pos_position = "VestFront"
            self.neg_position = "VestBack"
        else:
            self.pos_position = "VestBack"
            self.neg_position = "VestFront"

    def _start_bhaptics_client(self):
        url = "ws://127.0.0.1:15881/v2/feedbacks?app_id=assembly_x16&app_name=Pre_Study_Questionnaire"

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

    def trigger_positive(self, mode_override=None):
        mode = mode_override or self.pos_mode
        target_map = {
            "positive_1": self._pos_1_1p4hz,
            "positive_2": self._pos_2_upward_wave,
            "positive_3": self._pos_3_warm_swell
        }
        fn = target_map.get(mode, self._pos_1_1p4hz)
        threading.Thread(target=fn, daemon=True).start()

    def trigger_incorrect(self, mode_override=None):
        mode = mode_override or self.neg_mode
        target_map = {
            "negative_1": self._neg_1_0p5hz,
            "negative_2": self._neg_2_sharp_staccato,
            "negative_3": self._neg_3_chest_jitter
        }
        fn = target_map.get(mode, self._neg_1_0p5hz)
        threading.Thread(target=fn, daemon=True).start()

    # ------------------------------------------------------------------ positive patterns
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

    # ------------------------------------------------------------------ negative patterns
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


class PreStudyQuestionnaire(QWidget):
    """pre-study evaluation form with interactive haptic trigger buttons."""

    def __init__(self, feedback_ctrl):
        super().__init__()
        self.feedback = feedback_ctrl
        self.setWindowTitle("Pre-Study Haptic Evaluation Questionnaire")
        self.setMinimumSize(700, 800)

        self.setStyleSheet("""
            QWidget { background-color: #0F172A; color: #F8FAFC; font-family: Helvetica, Arial; }
            QGroupBox {
                background-color: #1E293B; border: 1px solid #334155; border-radius: 8px;
                margin-top: 12px; padding: 14px; font-weight: bold; font-size: 14px; color: #38BDF8;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLabel { color: #E2E8F0; font-size: 13px; font-weight: bold; }
            QLineEdit, QComboBox {
                background-color: #0F172A; color: #F8FAFC; border: 1px solid #475569;
                border-radius: 6px; padding: 6px; font-size: 13px;
            }
            QPushButton {
                background-color: #334155; color: #F8FAFC; border: 1px solid #64748B;
                border-radius: 6px; padding: 7px 14px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #475569; }
            QPushButton#triggerBtn {
                background-color: #0284C7; border-color: #38BDF8; color: #FFFFFF;
            }
            QPushButton#triggerBtn:hover { background-color: #0369A1; }
            QPushButton#saveBtn {
                background-color: #16A34A; border-color: #22C55E; font-size: 16px; padding: 12px;
            }
            QPushButton#saveBtn:hover { background-color: #15803D; }
            QSlider::groove:horizontal {
                height: 8px; background: #334155; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #38BDF8; border: 2px solid #F8FAFC; width: 18px;
                margin: -5px 0; border-radius: 9px;
            }
        """)

        main_layout = QVBoxLayout(self)

        # Scroll container for small displays
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)
        scroll_layout.setContentsMargins(16, 16, 16, 16)

        # Title Header
        title_lbl = QLabel("PRE-STUDY HAPTIC EVALUATION")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #38BDF8;")
        title_lbl.setAlignment(Qt.AlignCenter)
        scroll_layout.addWidget(title_lbl)

        # Participant & Mapping Setup Group
        setup_group = QGroupBox("Participant Setup")
        setup_form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter subject ID or name")
        setup_form.addRow(QLabel("Participant Name / ID:"), self.name_input)

        self.map_combo = QComboBox()
        self.map_combo.addItem("Correct -> Back  |  Incorrect -> Front", "correct_back")
        self.map_combo.addItem("Correct -> Front |  Incorrect -> Back", "correct_front")
        self.map_combo.currentIndexChanged.connect(self._on_mapping_change)
        setup_form.addRow(QLabel("Location Mapping Used:"), self.map_combo)

        setup_group.setLayout(setup_form)
        scroll_layout.addWidget(setup_group)

        # Selection of Stimuli
        stim_group = QGroupBox("Select Evaluated Stimuli")
        stim_form = QFormLayout()

        # Positive dropdown + test button
        pos_row = QHBoxLayout()
        self.pos_combo = QComboBox()
        self.pos_combo.addItem("positive_1  (1.4 Hz Rhythmic Pulse)", "positive_1")
        self.pos_combo.addItem("positive_2  (Upward Spatial Wave)", "positive_2")
        self.pos_combo.addItem("positive_3  (Warm Gaussian Swell)", "positive_3")
        btn_feel_pos_select = QPushButton("Feel Stimulus")
        btn_feel_pos_select.setObjectName("triggerBtn")
        btn_feel_pos_select.clicked.connect(self._trigger_current_positive)
        pos_row.addWidget(self.pos_combo, stretch=1)
        pos_row.addWidget(btn_feel_pos_select)
        stim_form.addRow(QLabel("Selected Positive Cue:"), pos_row)

        # Negative dropdown + test button
        neg_row = QHBoxLayout()
        self.neg_combo = QComboBox()
        self.neg_combo.addItem("negative_1  (0.5 Hz Heavy Thud)", "negative_1")
        self.neg_combo.addItem("negative_2  (4 Hz Sharp Staccato)", "negative_2")
        self.neg_combo.addItem("negative_3  (5 Hz Left/Right Jitter)", "negative_3")
        btn_feel_neg_select = QPushButton("Feel Stimulus")
        btn_feel_neg_select.setObjectName("triggerBtn")
        btn_feel_neg_select.clicked.connect(self._trigger_current_negative)
        neg_row.addWidget(self.neg_combo, stretch=1)
        neg_row.addWidget(btn_feel_neg_select)
        stim_form.addRow(QLabel("Selected Negative Cue:"), neg_row)

        stim_group.setLayout(stim_form)
        scroll_layout.addWidget(stim_group)

        # Task Efficiency Question Group
        eff_group = QGroupBox("Overall Task Efficiency")
        eff_layout = QVBoxLayout()
        eff_lbl = QLabel("Which stimulus let you do the task more efficiently?")
        self.eff_combo = QComboBox()
        self.eff_combo.addItem("Positive Cue")
        self.eff_combo.addItem("Negative Cue")
        self.eff_combo.addItem("Both Equally")
        self.eff_combo.addItem("Neither / No Preference")
        eff_layout.addWidget(eff_lbl)
        eff_layout.addWidget(self.eff_combo)
        eff_group.setLayout(eff_layout)
        scroll_layout.addWidget(eff_group)

        # Positive Cue Assessment Group
        pos_group = QGroupBox("Assessment: Positive Stimulus")
        pos_form = QFormLayout()

        btn_feel_pos_again = QPushButton("Feel Positive Cue Again")
        btn_feel_pos_again.setObjectName("triggerBtn")
        btn_feel_pos_again.clicked.connect(self._trigger_current_positive)
        pos_form.addRow(QLabel("Re-trigger Cue:"), btn_feel_pos_again)

        self.pos_intensity = QComboBox()
        self.pos_intensity.addItems(["Keep intensity", "Increase intensity", "Decrease intensity"])
        pos_form.addRow(QLabel("Guidance Intensity:"), self.pos_intensity)

        self.pos_length = QComboBox()
        self.pos_length.addItems(["Keep length", "Increase length", "Decrease length"])
        pos_form.addRow(QLabel("Guidance Length:"), self.pos_length)

        # Scale slider -10 to +10
        pos_slider_row = QHBoxLayout()
        self.pos_slider = QSlider(Qt.Horizontal)
        self.pos_slider.setRange(-10, 10)
        self.pos_slider.setValue(0)
        self.pos_slider_val = QLabel("0")
        self.pos_slider_val.setStyleSheet("color: #38BDF8; font-weight: bold; width: 30px;")
        self.pos_slider.valueChanged.connect(lambda v: self.pos_slider_val.setText(f"{v:+d}" if v != 0 else "0"))
        pos_slider_row.addWidget(self.pos_slider)
        pos_slider_row.addWidget(self.pos_slider_val)
        pos_form.addRow(QLabel("Position (-10 Very Neg to +10 Very Pos):"), pos_slider_row)

        pos_group.setLayout(pos_form)
        scroll_layout.addWidget(pos_group)

        # Negative Cue Assessment Group
        neg_group = QGroupBox("Assessment: Negative Stimulus")
        neg_form = QFormLayout()

        btn_feel_neg_again = QPushButton("Feel Negative Cue Again")
        btn_feel_neg_again.setObjectName("triggerBtn")
        btn_feel_neg_again.clicked.connect(self._trigger_current_negative)
        neg_form.addRow(QLabel("Re-trigger Cue:"), btn_feel_neg_again)

        self.neg_intensity = QComboBox()
        self.neg_intensity.addItems(["Keep intensity", "Increase intensity", "Decrease intensity"])
        neg_form.addRow(QLabel("Guidance Intensity:"), self.neg_intensity)

        self.neg_length = QComboBox()
        self.neg_length.addItems(["Keep length", "Increase length", "Decrease length"])
        neg_form.addRow(QLabel("Guidance Length:"), self.neg_length)

        # Scale slider -10 to +10
        neg_slider_row = QHBoxLayout()
        self.neg_slider = QSlider(Qt.Horizontal)
        self.neg_slider.setRange(-10, 10)
        self.neg_slider.setValue(0)
        self.neg_slider_val = QLabel("0")
        self.neg_slider_val.setStyleSheet("color: #F87171; font-weight: bold; width: 30px;")
        self.neg_slider.valueChanged.connect(lambda v: self.neg_slider_val.setText(f"{v:+d}" if v != 0 else "0"))
        neg_slider_row.addWidget(self.neg_slider)
        neg_slider_row.addWidget(self.neg_slider_val)
        neg_form.addRow(QLabel("Position (-10 Very Neg to +10 Very Pos):"), neg_slider_row)

        neg_group.setLayout(neg_form)
        scroll_layout.addWidget(neg_group)

        # Save Button
        btn_save = QPushButton("Save Evaluation Answers")
        btn_save.setObjectName("saveBtn")
        btn_save.clicked.connect(self._save_answers)
        scroll_layout.addWidget(btn_save)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _on_mapping_change(self):
        self.feedback.set_modes(
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData()
        )

    def _trigger_current_positive(self):
        self.feedback.set_modes(
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData()
        )
        self.feedback.trigger_positive()

    def _trigger_current_negative(self):
        self.feedback.set_modes(
            self.pos_combo.currentData(),
            self.neg_combo.currentData(),
            self.map_combo.currentData()
        )
        self.feedback.trigger_incorrect()

    def _save_answers(self):
        participant_name = self.name_input.text().strip()
        if not participant_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a Participant Name or ID before saving.")
            return

        # Prepare survey payload
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data = {
            "participant": participant_name,
            "timestamp": timestamp,
            "location_mapping": self.map_combo.currentData(),
            "more_efficient_stimulus": self.eff_combo.currentText(),
            "positive_stimulus_eval": {
                "selected_pattern": self.pos_combo.currentData(),
                "intensity_preference": self.pos_intensity.currentText(),
                "length_preference": self.pos_length.currentText(),
                "valence_score": self.pos_slider.value()
            },
            "negative_stimulus_eval": {
                "selected_pattern": self.neg_combo.currentData(),
                "intensity_preference": self.neg_intensity.currentText(),
                "length_preference": self.neg_length.currentText(),
                "valence_score": self.neg_slider.value()
            }
        }

        # Ensure "answers pre study" directory exists
        os.makedirs(ANSWERS_DIR, exist_ok=True)

        # Sanitize name for filename
        clean_name = "".join(c for c in participant_name if c.isalnum() or c in ("_", "-")).rstrip()
        filename = f"pre_study_{clean_name}_{timestamp}.json"
        filepath = os.path.join(ANSWERS_DIR, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            QMessageBox.information(
                self, "Answers Saved",
                f"Pre-study evaluation for '{participant_name}' saved successfully!\nFile: {filepath}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save answers file: {e}")

    def closeEvent(self, event):
        self.feedback.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    feedback = FeedbackController()
    window = PreStudyQuestionnaire(feedback)
    window.show()
    sys.exit(app.exec_())