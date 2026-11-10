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
    """Manages persistent bhaptics player websocket connection and stimulus variants."""

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
            print("Connected to bhaptics player.")

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
            print(f"bHaptics send error: {e}")

    def trigger_correct(self, mode_override=None):
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

    def feel_spatial_mapping(self):
        """Triggers a correct cue followed by an incorrect cue to feel the spatial mapping layout."""
        def sequence():
            self.trigger_correct()
            time.sleep(0.7)
            self.trigger_incorrect()
        threading.Thread(target=sequence, daemon=True).start()

    # ------------------------------------------------------------------ Correct patterns
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

    # ------------------------------------------------------------------ Incorrect patterns
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
    """Pre-study evaluation form with interactive haptic trigger buttons."""

    CORRECT_CUES = [
        ("positive_1", "Correct Cue 1: 1.4 Hz Rhythmic Pulse"),
        ("positive_2", "Correct Cue 2: Upward Spatial Wave"),
        ("positive_3", "Correct Cue 3: Warm Gaussian Swell")
    ]

    INCORRECT_CUES = [
        ("negative_1", "Incorrect Cue 1: 0.5 Hz Heavy Thud"),
        ("negative_2", "Incorrect Cue 2: 4 Hz Sharp Staccato"),
        ("negative_3", "Incorrect Cue 3: 5 Hz Left/Right Jitter")
    ]

    def __init__(self, feedback_ctrl):
        super().__init__()
        self.feedback = feedback_ctrl
        self.setWindowTitle("Pre-Study Haptic Evaluation Questionnaire")
        self.setMinimumSize(780, 900)

        self.setStyleSheet("""
            QWidget { background-color: #0F172A; color: #F8FAFC; font-family: Helvetica, Arial; }
            QGroupBox {
                background-color: #1E293B; border: 1px solid #334155; border-radius: 8px;
                margin-top: 12px; padding: 14px; font-weight: bold; font-size: 16px; color: #38BDF8;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLabel { color: #E2E8F0; font-size: 15px; font-weight: bold; }
            QLineEdit, QComboBox {
                background-color: #0F172A; color: #F8FAFC; border: 1px solid #475569;
                border-radius: 6px; padding: 6px; font-size: 15px;
            }
            QPushButton {
                background-color: #334155; color: #F8FAFC; border: 1px solid #64748B;
                border-radius: 6px; padding: 7px 14px; font-size: 15px; font-weight: bold;
            }
            QPushButton:hover { background-color: #475569; }
            QPushButton#triggerBtn {
                background-color: #0284C7; border-color: #38BDF8; color: #FFFFFF;
            }
            QPushButton#triggerBtn:hover { background-color: #0369A1; }
            QPushButton#mapFeelBtn {
                background-color: #D97706; border-color: #F59E0B; color: #FFFFFF;
            }
            QPushButton#mapFeelBtn:hover { background-color: #B45309; }
            QPushButton#saveBtn {
                background-color: #16A34A; border-color: #22C55E; font-size: 18px; padding: 12px;
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)
        scroll_layout.setContentsMargins(16, 16, 16, 16)

        # Title Header
        title_lbl = QLabel("PRE-STUDY HAPTIC EVALUATION")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #38BDF8;")
        title_lbl.setAlignment(Qt.AlignCenter)
        scroll_layout.addWidget(title_lbl)

        # Section 1: Participant Spatial Mapping Setup
        setup_group = QGroupBox("Participant Spatial Mapping Setup")
        setup_form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter subject ID or name")
        setup_form.addRow(QLabel("Participant Name / ID:"), self.name_input)

        # Current Test Mapping + Feel Button Row
        map_row = QHBoxLayout()
        self.map_combo = QComboBox()
        self.map_combo.addItem("Correct -> Back  |  Incorrect -> Front", "correct_back")
        self.map_combo.addItem("Correct -> Front |  Incorrect -> Back", "correct_front")
        self.map_combo.currentIndexChanged.connect(self._on_mapping_change)

        btn_feel_map = QPushButton("Feel Mapping")
        btn_feel_map.setObjectName("mapFeelBtn")
        btn_feel_map.setToolTip("Feel how Correct and Incorrect cues feel in their assigned locations")
        btn_feel_map.clicked.connect(self._feel_mapping_action)

        map_row.addWidget(self.map_combo, stretch=1)
        map_row.addWidget(btn_feel_map)
        setup_form.addRow(QLabel("Current Test Mapping:"), map_row)

        # Preferred Spatial Mapping Question
        self.pref_map_combo = QComboBox()
        self.pref_map_combo.addItem("Correct in Back / Incorrect in Front", "correct_back")
        self.pref_map_combo.addItem("Correct in Front / Incorrect in Back", "correct_front")
        setup_form.addRow(QLabel("Preferred Spatial Mapping:"), self.pref_map_combo)

        # Guidance Length Drop-down
        self.guidance_length_combo = QComboBox()
        self.guidance_length_combo.addItems(["Keep length", "Increase length", "Decrease length"])
        setup_form.addRow(QLabel("Duration of cues:"), self.guidance_length_combo)

        setup_group.setLayout(setup_form)
        scroll_layout.addWidget(setup_group)

        # Section 2: Assessment: Correct Cues
        correct_group = QGroupBox("Assessment: Correct Cues")
        correct_layout = QVBoxLayout()

        self.correct_eval_widgets = {}
        for key, label_text in self.CORRECT_CUES:
            sub_box = QGroupBox(label_text)
            sub_form = QFormLayout()

            # Feel Cue button
            btn_feel = QPushButton("Feel Cue")
            btn_feel.setObjectName("triggerBtn")
            btn_feel.clicked.connect(lambda _, k=key: self._trigger_correct(k))
            sub_form.addRow(QLabel("Trigger Vibration:"), btn_feel)

            # Intensity drop-down
            intensity_cb = QComboBox()
            intensity_cb.addItems(["Keep intensity", "Increase intensity", "Decrease intensity"])
            sub_form.addRow(QLabel("Guidance Intensity:"), intensity_cb)

            # Usefulness Slider (0 to 10)
            slider_row = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 10)
            slider.setValue(0)
            val_lbl = QLabel("0")
            val_lbl.setStyleSheet("color: #38BDF8; font-weight: bold; width: 35px;")
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(str(v)))
            slider_row.addWidget(slider)
            slider_row.addWidget(val_lbl)
            sub_form.addRow(
                QLabel("Usefulness in detecting Correct answer ((0) not useful at all to (10) very useful):"),
                slider_row
            )

            sub_box.setLayout(sub_form)
            correct_layout.addWidget(sub_box)

            self.correct_eval_widgets[key] = {
                "intensity": intensity_cb,
                "usefulness_slider": slider
            }

        # Overall Correct Questions
        correct_meta_box = QGroupBox("Correct Cues Comparison")
        meta_correct_form = QFormLayout()

        self.best_correct_combo = QComboBox()
        for key, text in self.CORRECT_CUES:
            self.best_correct_combo.addItem(text, key)
        meta_correct_form.addRow(QLabel("Which correct cue did you like the most?"), self.best_correct_combo)

        self.diff_correct_combo = QComboBox()
        self.diff_correct_combo.addItem("One cue was significantly better for perceiving the correct answer", "significantly_better")
        self.diff_correct_combo.addItem("All correct cues felt almost the same", "almost_same")
        meta_correct_form.addRow(QLabel("Difference in perception between correct cues:"), self.diff_correct_combo)

        correct_meta_box.setLayout(meta_correct_form)
        correct_layout.addWidget(correct_meta_box)

        correct_group.setLayout(correct_layout)
        scroll_layout.addWidget(correct_group)

        # Section 3: Assessment: Incorrect Cues
        incorrect_group = QGroupBox("Assessment: Incorrect Cues")
        incorrect_layout = QVBoxLayout()

        self.incorrect_eval_widgets = {}
        for key, label_text in self.INCORRECT_CUES:
            sub_box = QGroupBox(label_text)
            sub_form = QFormLayout()

            # Feel Cue button
            btn_feel = QPushButton("Feel Cue")
            btn_feel.setObjectName("triggerBtn")
            btn_feel.clicked.connect(lambda _, k=key: self._trigger_incorrect(k))
            sub_form.addRow(QLabel("Trigger Vibration:"), btn_feel)

            # Intensity drop-down
            intensity_cb = QComboBox()
            intensity_cb.addItems(["Keep intensity", "Increase intensity", "Decrease intensity"])
            sub_form.addRow(QLabel("Guidance Intensity:"), intensity_cb)

            # Usefulness Slider (0 to 10)
            slider_row = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 10)
            slider.setValue(0)
            val_lbl = QLabel("0")
            val_lbl.setStyleSheet("color: #F87171; font-weight: bold; width: 35px;")
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(str(v)))
            slider_row.addWidget(slider)
            slider_row.addWidget(val_lbl)
            sub_form.addRow(
                QLabel("Usefulness in detecting Incorrect answer ((0) not useful at all to (10) very useful):"),
                slider_row
            )

            sub_box.setLayout(sub_form)
            incorrect_layout.addWidget(sub_box)

            self.incorrect_eval_widgets[key] = {
                "intensity": intensity_cb,
                "usefulness_slider": slider
            }

        # Overall Incorrect Questions
        incorrect_meta_box = QGroupBox("Incorrect Cues Comparison")
        meta_incorrect_form = QFormLayout()

        self.best_incorrect_combo = QComboBox()
        for key, text in self.INCORRECT_CUES:
            self.best_incorrect_combo.addItem(text, key)
        meta_incorrect_form.addRow(QLabel("Which incorrect cue did you like the most?"), self.best_incorrect_combo)

        self.diff_incorrect_combo = QComboBox()
        self.diff_incorrect_combo.addItem("One cue was significantly better for perceiving the incorrect answer", "significantly_better")
        self.diff_incorrect_combo.addItem("All incorrect cues felt almost the same", "almost_same")
        meta_incorrect_form.addRow(QLabel("Difference in perception between incorrect cues:"), self.diff_incorrect_combo)

        incorrect_meta_box.setLayout(meta_incorrect_form)
        incorrect_layout.addWidget(incorrect_meta_box)

        incorrect_group.setLayout(incorrect_layout)
        scroll_layout.addWidget(incorrect_group)

        # Save Button
        btn_save = QPushButton("Save Evaluation Answers")
        btn_save.setObjectName("saveBtn")
        btn_save.clicked.connect(self._save_answers)
        scroll_layout.addWidget(btn_save)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _on_mapping_change(self):
        self.feedback.set_modes(
            "positive_1",
            "negative_1",
            self.map_combo.currentData()
        )

    def _feel_mapping_action(self):
        self._on_mapping_change()
        self.feedback.feel_spatial_mapping()

    def _trigger_correct(self, key):
        self.feedback.set_modes(key, "negative_1", self.map_combo.currentData())
        self.feedback.trigger_correct(key)

    def _trigger_incorrect(self, key):
        self.feedback.set_modes("positive_1", key, self.map_combo.currentData())
        self.feedback.trigger_incorrect(key)

    def _save_answers(self):
        participant_name = self.name_input.text().strip()
        if not participant_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a Participant Name or ID before saving.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Gather evaluations for all 3 correct cues
        correct_cues_eval = {}
        for key, _ in self.CORRECT_CUES:
            correct_cues_eval[key] = {
                "guidance_intensity": self.correct_eval_widgets[key]["intensity"].currentText(),
                "usefulness_score": self.correct_eval_widgets[key]["usefulness_slider"].value()
            }

        # Gather evaluations for all 3 incorrect cues
        incorrect_cues_eval = {}
        for key, _ in self.INCORRECT_CUES:
            incorrect_cues_eval[key] = {
                "guidance_intensity": self.incorrect_eval_widgets[key]["intensity"].currentText(),
                "usefulness_score": self.incorrect_eval_widgets[key]["usefulness_slider"].value()
            }

        data = {
            "participant": participant_name,
            "timestamp": timestamp,
            "spatial_mapping_setup": {
                "current_test_mapping": self.map_combo.currentData(),
                "preferred_spatial_mapping": self.pref_map_combo.currentData(),
                "guidance_length_preference": self.guidance_length_combo.currentText()
            },
            "assessment_correct_cues": {
                "cues": correct_cues_eval,
                "most_liked_cue": self.best_correct_combo.currentData(),
                "perception_difference": self.diff_correct_combo.currentData()
            },
            "assessment_incorrect_cues": {
                "cues": incorrect_cues_eval,
                "most_liked_cue": self.best_incorrect_combo.currentData(),
                "perception_difference": self.diff_incorrect_combo.currentData()
            }
        }

        # Ensure "answers pre study" directory exists
        os.makedirs(ANSWERS_DIR, exist_ok=True)

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