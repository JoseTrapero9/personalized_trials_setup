"""Dual-task split screen: game (left) + battery assembly (right)."""

import csv
import os
import time

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from audio import audio_sys
from config import (
    DELIVERY_WINDOW_SECONDS,
    LOG_TRAINING_CSV,
    MAX_ROUNDS_PER_CONDITION,
    RETRIEVAL_SECONDS,
    TASK_SECONDS_DEFAULT,
    USE_RADIO_CONTAINER_CUES,
    WARNING_SECONDS,
    alarm_audio,
    assembly_seconds,
    base_dir,
    container1_audio,
    container2_audio,
    incorrect_audio
)
from game import RadioPanelGame
from lsl_markers import send_marker
from sequences import load_condition_sequence
from state import state
from texts import t
from ui_helpers import auto_fit_label, make_training_tag
from voice import VoiceDeliverListener


class DualTaskScreen(QWidget):
    def __init__(self, round_complete_cb, condition_complete_cb, get_scenario_cb):
        super().__init__()
        self.round_complete_cb = round_complete_cb
        self.condition_complete_cb = condition_complete_cb
        self.get_scenario_cb = get_scenario_cb

        # State machine: "PLAY_TO_CHECKPOINT" -> "RETRIEVAL_PAUSE" -> "DUAL_ASSEMBLY" -> "DELIVERY_PAUSE"
        self.phase = "PLAY_TO_CHECKPOINT"
        self.current_round = 0
        self.max_rounds = MAX_ROUNDS_PER_CONDITION
        self.container_toggle = True

        self.pause_ticks_left = 0
        self.assembly_ticks_left = TASK_SECONDS_DEFAULT
        self.alarm_triggered = False
        self.active_collection_pt = 1
        self.task_start_time = 0.0
        self.current_task_info = ""
        self.warn_visible = False

        self.evaluated = False
        self.assembly_status = "none"
        self.pending_log = None
        self.session_csv_path = None
        self.sequence = []
        self.sequence_file = ""

        self.phase_timer = QTimer(self)
        self.phase_timer.timeout.connect(self._on_phase_timer_tick)

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._on_blink_tick)

        self.voice_listener = VoiceDeliverListener()
        self.voice_listener.deliver_detected.connect(self.trigger_voice_deliver)

        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)

        # LEFT PANEL: plant-radio button game
        self.game_widget = RadioPanelGame()
        self.game_widget.checkpoint_reached.connect(self.start_retrieval_checkpoint)
        main_layout.addWidget(self.game_widget, stretch=6)

        # RIGHT PANEL: Battery Task + Rules
        self.right_container = QFrame()
        self.right_container.setFrameShape(QFrame.StyledPanel)
        self.right_container.setStyleSheet("background-color: white; border-radius: 12px;")
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(20, 16, 20, 16)
        right_layout.setSpacing(10)

        self.training_tag = make_training_tag()
        right_layout.addWidget(self.training_tag, alignment=Qt.AlignCenter)

        self.round_label = QLabel("ROUND 1 / 8")
        self.round_label.setFont(QFont("Helvetica", 20, QFont.Bold))
        self.round_label.setStyleSheet("color: #475467; letter-spacing: 1px;")
        self.round_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.round_label)

        # System Failed Banner on the Battery Screen
        self.system_failed_label = QLabel("")
        self.system_failed_label.setFont(QFont("Helvetica", 22, QFont.Bold))
        self.system_failed_label.setAlignment(Qt.AlignCenter)
        self.system_failed_label.setWordWrap(True)
        self.system_failed_label.setStyleSheet(
            "color: white; background-color: #D92D20; border-radius: 10px; padding: 12px;"
        )
        self.system_failed_label.hide()
        right_layout.addWidget(self.system_failed_label)

        self.header_label = QLabel("ADVANCE TO CHECKPOINT")
        self.header_label.setFont(QFont("Helvetica", 22, QFont.Bold))
        self.header_label.setStyleSheet("color: #555;")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setWordWrap(True)
        right_layout.addWidget(self.header_label)

        self.timer_label = QLabel("")
        self.timer_label.setFont(QFont("Helvetica", 72, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #111;")
        right_layout.addWidget(self.timer_label)

        self.warning_label = QLabel("")
        self.warning_label.setFont(QFont("Helvetica", 32, QFont.Bold))
        self.warning_label.setStyleSheet("color: red;")
        self.warning_label.setAlignment(Qt.AlignCenter)
        self.warning_label.setFixedHeight(45)
        right_layout.addWidget(self.warning_label)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.hide()
        right_layout.addWidget(self.image_label)

        self.target_sum_label = QLabel("")
        self.target_sum_label.setAlignment(Qt.AlignCenter)
        self.target_sum_label.setStyleSheet("font-weight: bold; color: #222;")
        right_layout.addWidget(self.target_sum_label)

        self.instruction_label = QLabel("")
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.instruction_label.setStyleSheet("font-weight: bold; color: #0056B3;")
        self.instruction_label.setWordWrap(True)
        right_layout.addWidget(self.instruction_label)

        right_layout.addStretch(1)

        # Rules Box embedded cleanly inside the Right Panel
        rules_box = QFrame()
        rules_box.setStyleSheet("background-color: #F8FAFC; border: 2px solid #E2E8F0; border-radius: 10px;")
        rules_layout = QHBoxLayout(rules_box)
        rules_layout.setContentsMargins(16, 10, 16, 10)

        colors_lbl = QLabel(
            "<b>Colors:</b><br>"
            "<font color='blue'>Blue:</font> 1 &nbsp;&nbsp; <font color='red'>Red:</font> 2<br>"
            "<font color='#B8860B'>Yellow:</font> 3 &nbsp;&nbsp; <font color='green'>Green:</font> 4"
        )
        colors_lbl.setFont(QFont("Helvetica", 18))

        slots_lbl = QLabel(
            "<b>Slots:</b><br>"
            "Slot 1 = ×1 &nbsp;|&nbsp; Slot 2 = ×2 &nbsp;|&nbsp; Slot 3 = ×3"
        )
        slots_lbl.setFont(QFont("Helvetica", 18))

        rules_layout.addWidget(colors_lbl)
        rules_layout.addWidget(slots_lbl)
        right_layout.addWidget(rules_box)

        self.handover_label = QLabel("")
        self.handover_label.setFont(QFont("Helvetica", 19))
        self.handover_label.setAlignment(Qt.AlignCenter)
        self.handover_label.setWordWrap(True)
        self.handover_label.setStyleSheet(
            "color: #1E293B; padding: 12px; background-color: #E2E8F0; border-radius: 8px;"
        )
        right_layout.addWidget(self.handover_label)

        main_layout.addWidget(self.right_container, stretch=5)
        self.right_container.hide()

    def start_condition_session(self, max_rounds: int):
        self.flush_pending_log()
        self.max_rounds = max_rounds
        self.current_round = 0
        self.container_toggle = True
        self.session_csv_path = None
        if state.training_active and state.training_sequence:
            self.sequence, self.sequence_file = state.training_sequence, "training"
        else:
            self.sequence, self.sequence_file = load_condition_sequence(state.subject_number, state.current_condition)
        send_marker(f"Sequence_File_{self.sequence_file}")
        self.system_failed_label.hide()
        self.system_failed_label.setText(t("system_failed"))
        self.right_container.hide()

        if state.training_active:
            self.training_tag.show()
        else:
            self.training_tag.hide()

        self.handover_label.setText(t("advance"))
        self.game_widget.start()
        self._enter_play_to_checkpoint()
        self.setFocus()

    def _enter_play_to_checkpoint(self):
        self.phase = "PLAY_TO_CHECKPOINT"
        self.voice_listener.set_enabled(False)
        self.phase_timer.stop()
        self.blink_timer.stop()
        self.system_failed_label.hide()
        self.game_widget.set_system_failed(False)
        self.game_widget.set_pause(False)
        self.game_widget.set_counting(True)
        self.game_widget.reset_checkpoint_counter()

        # Keep full focus on the radio game until the checkpoint splits the screen
        self.right_container.hide()

    def start_retrieval_checkpoint(self):
        """Triggered by the game after PROBLEMS_PER_CHECKPOINT radio problems (solved or not)."""
        if self.phase != "PLAY_TO_CHECKPOINT":
            return

        self.current_round += 1
        self.phase = "RETRIEVAL_PAUSE"
        self.pause_ticks_left = RETRIEVAL_SECONDS

        target_container = "I" if self.container_toggle else "II"
        send_marker(f"Checkpoint_Retrieval_Start_Round_{self.current_round}_Container_{target_container}")

        self.game_widget.set_counting(False)
        self.game_widget.set_pause(
            True,
            title=t("checkpoint_title", r=self.current_round, m=self.max_rounds),
            subtitle=t("checkpoint_sub", c=target_container),
            seconds_left=self.pause_ticks_left
        )
        cue = "container_1" if self.container_toggle else "container_2"
        if not (USE_RADIO_CONTAINER_CUES and self.game_widget.announce(cue)):
            audio_sys.play_participant(container1_audio if self.container_toggle else container2_audio)
        self.container_toggle = not self.container_toggle
        self.phase_timer.start(1000)

    def _start_dual_assembly_phase(self):
        """Splits the screen: battery task on the right while the radio game keeps going."""
        self.phase = "DUAL_ASSEMBLY"
        self.game_widget.set_pause(False)
        self.right_container.show()

        self.assembly_ticks_left = assembly_seconds(self.get_scenario_cb())

        self.evaluated = False
        self.assembly_status = "none"
        self.pending_log = None
        self.alarm_triggered = False
        self.active_collection_pt = 1 if (self.current_round % 2 != 0) else 2
        self.task_start_time = time.perf_counter()
        self.warn_visible = False

        seq = self.sequence
        idx = (self.current_round - 1) % len(seq)
        mode, p1, p2 = seq[idx]

        self.round_label.setText(t("round", r=self.current_round, m=self.max_rounds))
        self.header_label.setText(t("solve_header"))
        self.system_failed_label.hide()
        self.game_widget.set_system_failed(False)

        if mode == "image":
            self.target_sum_label.hide()
            self.instruction_label.hide()
            self.image_label.show()
            self.current_task_info = f"image_{p1}"
            img_path = os.path.join(base_dir, "workpieces", p1)
            if os.path.exists(img_path):
                pixmap = QPixmap(img_path)
                self.image_label.setPixmap(pixmap.scaledToWidth(260, Qt.SmoothTransformation))
            else:
                self.image_label.setText(f"[Image: {p1}]")
        else:
            self.image_label.clear()
            self.image_label.hide()
            self.target_sum_label.show()
            self.instruction_label.show()
            self.current_task_info = f"sum_{p1}_{p2}"
            auto_fit_label(self.target_sum_label, f"Sum must be {p1}", max_size=34, min_size=22)
            auto_fit_label(self.instruction_label, str(p2), max_size=36, min_size=20)

        self.handover_label.setText(self._deliver_hint())

        self.timer_label.setStyleSheet("color: #111;")
        self.timer_label.setText(f"{self.assembly_ticks_left} s")
        self.warning_label.setText("")
        self.blink_timer.stop()

        self.voice_listener.set_enabled(True)
        send_marker(f"Dual_Workpiece_Task_Started_Round_{self.current_round}_Type_{self.current_task_info}")
        self.phase_timer.start(1000)

    def trigger_voice_deliver(self):
        """Called when 'deliver' is spoken (or 'D' is pressed) during assembly."""
        if self.phase != "DUAL_ASSEMBLY":
            return

        self.phase = "DELIVERY_PAUSE"
        self.pause_ticks_left = DELIVERY_WINDOW_SECONDS
        self.voice_listener.set_enabled(False)

        pt_name, key_hint = self._point_names()

        send_marker(f"Voice_Deliver_Activated_Round_{self.current_round}")
        self.game_widget.set_pause(
            True,
            title=t("delivery_title", s=DELIVERY_WINDOW_SECONDS),
            subtitle=t("delivery_sub", pt=pt_name, key=key_hint),
            seconds_left=self.pause_ticks_left
        )
        self.handover_label.setText(t("delivery_active", s=self.pause_ticks_left, pt=pt_name, key=key_hint))

    def _on_phase_timer_tick(self):
        if self.phase == "RETRIEVAL_PAUSE":
            self.pause_ticks_left -= 1
            if self.pause_ticks_left <= 0:
                self.phase_timer.stop()
                send_marker("Retrieval_Finished")
                self._start_dual_assembly_phase()
            else:
                self.game_widget.set_pause_seconds(self.pause_ticks_left)

        elif self.phase == "DUAL_ASSEMBLY":
            self.assembly_ticks_left -= 1
            self._update_assembly_countdown()

        elif self.phase == "DELIVERY_PAUSE":
            self.pause_ticks_left -= 1
            # Keep assembly timer ticking in the background if not yet at 0
            if self.assembly_ticks_left > 0:
                self.assembly_ticks_left -= 1
                self._update_assembly_countdown()

            if self.pause_ticks_left <= 0:
                # If participant didn't press the button within 5s, resume traffic and let them say "deliver" again
                send_marker("Delivery_Window_Expired_Resuming_Traffic")
                self.phase = "DUAL_ASSEMBLY"
                self.game_widget.set_pause(False)
                self.voice_listener.set_enabled(True)
                self.handover_label.setText(self._deliver_hint())
            else:
                self.game_widget.set_pause_seconds(self.pause_ticks_left)

    def _update_assembly_countdown(self):
        if 0 < self.assembly_ticks_left <= WARNING_SECONDS:
            self.timer_label.setStyleSheet("color: red;")
            if not self.blink_timer.isActive():
                self.warn_visible = True
                self.warning_label.setText(t("warning_finish"))
                self.blink_timer.start(250)

        if self.assembly_ticks_left <= 0:
            self.timer_label.setText("0 s")
            self.timer_label.setStyleSheet("color: red;")

            if not self.blink_timer.isActive():
                self.warn_visible = True
                self.blink_timer.start(250)

            if not self.alarm_triggered:
                self.alarm_triggered = True
                send_marker("Workpiece_Task_Overtime_System_Failed_Started")
                audio_sys.start_looping_alarm(alarm_audio, volume=0.9)
                self.system_failed_label.show()
                self.game_widget.set_system_failed(True, True)
        else:
            self.timer_label.setText(f"{self.assembly_ticks_left} s")

    def _on_blink_tick(self):
        self.warn_visible = not self.warn_visible
        if self.alarm_triggered:
            self.warning_label.setText(t("failed_short") if self.warn_visible else "")
            self.game_widget.set_system_failed(True, self.warn_visible)
            if self.warn_visible:
                self.system_failed_label.setStyleSheet(
                    "color: white; background-color: #D92D20; border-radius: 10px; padding: 12px;"
                )
            else:
                self.system_failed_label.setStyleSheet(
                    "color: white; background-color: #7F1D1D; border-radius: 10px; padding: 12px;"
                )
        else:
            self.warning_label.setText(t("warning_finish") if self.warn_visible else "")

    def handover_received(self, point_pressed: int):
        """Accepts Left (Point 1) or Right (Point 2) button press during assembly or delivery window."""
        if self.phase not in ["DUAL_ASSEMBLY", "DELIVERY_PAUSE"]:
            return
        if self.active_collection_pt is None or point_pressed != self.active_collection_pt:
            return

        self.phase_timer.stop()
        self.blink_timer.stop()
        self.voice_listener.set_enabled(False)
        self.warning_label.setText("")
        self.system_failed_label.hide()
        self.game_widget.set_system_failed(False)
        self.game_widget.set_pause(False)

        elapsed = time.perf_counter() - self.task_start_time

        if self.alarm_triggered:
            audio_sys.stop_looping_alarm()
            send_marker("Workpiece_Task_Overtime_System_Failed_Stopped")
        else:
            # Speed bonus for delivering before system failure
            self.game_widget.score += 75

        send_marker(f"Handover_Confirmed_Point_{point_pressed}_Duration_{round(elapsed, 3)}")

        log_data = {
            "round": self.current_round,
            "task_info": self.current_task_info,
            "elapsed": elapsed,
            "point_pressed": point_pressed,
            "alarm_triggered": self.alarm_triggered,
            "assembly_status": self.assembly_status,
            "game_score": self.game_widget.score
        }

        if self.evaluated:
            self._write_csv_row(log_data)
            self.pending_log = None
        else:
            self.pending_log = log_data

        self.active_collection_pt = None
        self.round_complete_cb(point_pressed)

        # Check if all 8 rounds (or training rounds) are complete
        if self.current_round >= self.max_rounds:
            self.game_widget.stop()
            self.flush_pending_log()
            self.condition_complete_cb(self.game_widget.score)
        else:
            self.handover_label.setText(t("advance"))
            self._enter_play_to_checkpoint()

    def record_evaluation(self, is_correct: bool, source: str = "researcher"):
        if self.current_round == 0 or self.evaluated:
            return

        self.evaluated = True
        self.assembly_status = "correct" if is_correct else "incorrect"
        send_marker(f"Assembly_Evaluated_{self.assembly_status}")
        send_marker(f"Assembly_Evaluation_Source_{source}_Round_{self.current_round}")

        if is_correct:
            self.game_widget.score += 100
        else:
            audio_sys.play_both(incorrect_audio)

        if self.pending_log is not None:
            self.pending_log["assembly_status"] = self.assembly_status
            self.pending_log["game_score"] = self.game_widget.score
            self._write_csv_row(self.pending_log)
            self.pending_log = None

    def remote_verdict(self, round_number: int, is_correct: bool):
        """Verdict from live_evaluator.py (camera PC). Only used for the round it belongs to."""
        if round_number != self.current_round:
            send_marker(f"Remote_Verdict_Ignored_Round_{round_number}_Current_{self.current_round}")
            return
        self.record_evaluation(is_correct, source="camera")

    def flush_pending_log(self):
        if self.pending_log is not None:
            self._write_csv_row(self.pending_log)
            self.pending_log = None

    def _write_csv_row(self, log_dict):
        if state.training_active and not LOG_TRAINING_CSV:
            return

        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)

        if self.session_csv_path is None:
            try:
                subj_int = int(state.subject_number)
                subj_str = f"s{subj_int:02d}"
            except ValueError:
                subj_str = f"s_{state.subject_number}"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{subj_str}_{state.current_condition}_{timestamp}.csv"
            self.session_csv_path = os.path.join(log_dir, filename)

        file_exists = os.path.isfile(self.session_csv_path)
        with open(self.session_csv_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "subject", "condition", "difficulty", "round",
                    "task_info", "time_taken_s", "handover_point",
                    "overtime_alarm", "assembly_status", "game_score", "game_mode"
                ])
            writer.writerow([
                state.subject_number,
                state.current_condition,
                state.difficulty,
                log_dict["round"],
                log_dict["task_info"],
                round(log_dict["elapsed"], 3),
                log_dict["point_pressed"],
                log_dict["alarm_triggered"],
                log_dict["assembly_status"],
                log_dict["game_score"],
                state.game_mode
            ])

    def _point_names(self):
        n = 1 if self.active_collection_pt == 1 else 2
        return t("point", n=n), t("key_left") if n == 1 else t("key_right")

    def _deliver_hint(self):
        pt_name, key_hint = self._point_names()
        return t("deliver_hint", s=DELIVERY_WINDOW_SECONDS, pt=pt_name, key=key_hint)

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key_Left:
            self.game_widget.press(0)
        elif event.key() == Qt.Key_Up:
            self.game_widget.press(1)
        elif event.key() == Qt.Key_Right:
            self.game_widget.press(2)
        elif event.key() == Qt.Key_D:
            # Keyboard fallback for voice recognition "deliver"
            self.trigger_voice_deliver()
        else:
            super().keyPressEvent(event)
