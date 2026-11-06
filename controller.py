"""Main window: owns the screens and routes between them."""

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication, QShortcut, QStackedWidget, QVBoxLayout, QWidget

from audio import audio_sys
from config import (
    MAX_ROUNDS_PER_CONDITION,
    TRAINING_ROUNDS,
    USE_REMOTE_EVALUATOR,
    mistake_audio,
    mode_audio_haptic,
    mode_audio_only,
    mode_baseline,
    mode_haptic_only,
    mode_robot_fast,
    mode_robot_slow
)
from evaluator_link import EvaluatorLink
from haptics import activate_haptic_vest
from lsl_markers import send_marker
from robot import send_point_to_robot, set_robot_speed
from screens.dual_task_screen import DualTaskScreen
from screens.scoreboard_screen import ArcadeScoreboardScreen
from screens.setup_screen import setupscreen
from screens.start_screen import startscreen
from screens.tutorial_screen import tutorialscreen
from sequences import build_training_sequence
from state import state


class paradigmcontroller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dual-Task Assembly and Collaboration Paradigm")
        self.mistake_on_cooldown = False

        self.stacked_widget = QStackedWidget()
        self.setup_screen = setupscreen(self.setup_finished_callback)
        self.tutorial_screen = tutorialscreen(self.tutorial_finished_callback)
        self.start_screen = startscreen(self.start_experiment_tracking)
        self.dual_task_screen = DualTaskScreen(
            round_complete_cb=self.on_handover_complete,
            condition_complete_cb=self.on_condition_complete,
            get_scenario_cb=self.get_current_scenario
        )
        self.scoreboard_screen = ArcadeScoreboardScreen(self.return_to_setup)

        self.stacked_widget.addWidget(self.setup_screen)       # 0
        self.stacked_widget.addWidget(self.tutorial_screen)    # 1
        self.stacked_widget.addWidget(self.start_screen)       # 2
        self.stacked_widget.addWidget(self.dual_task_screen)   # 3
        self.stacked_widget.addWidget(self.scoreboard_screen)  # 4

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)

        # Global Shortcuts
        self.quit_shortcut = QShortcut(QKeySequence("q"), self)
        self.quit_shortcut.activated.connect(QApplication.instance().quit)

        self.mistake_shortcut = QShortcut(QKeySequence("F12"), self)
        self.mistake_shortcut.activated.connect(self.trigger_mistake)

        self.f13_shortcut = QShortcut(QKeySequence("F13"), self)
        self.f13_shortcut.activated.connect(lambda: self.on_point_button(1))

        self.f14_shortcut = QShortcut(QKeySequence("F14"), self)
        self.f14_shortcut.activated.connect(lambda: self.on_point_button(2))

        # Manual evaluation keys only without the camera evaluator (which judges every assembly itself)
        if not USE_REMOTE_EVALUATOR:
            self.y_shortcut = QShortcut(QKeySequence("y"), self)
            self.y_shortcut.activated.connect(lambda: self.dual_task_screen.record_evaluation(True))

            self.c_shortcut = QShortcut(QKeySequence("c"), self)
            self.c_shortcut.activated.connect(lambda: self.dual_task_screen.record_evaluation(False))

        # Camera evaluator on the other PC (live_evaluator.py) - verdicts arrive over LSL
        self.evaluator_link = None
        if USE_REMOTE_EVALUATOR:
            self.evaluator_link = EvaluatorLink(parent=self)
            self.evaluator_link.verdict_received.connect(self.dual_task_screen.remote_verdict)
            self.evaluator_link.connection_changed.connect(
                lambda ok: send_marker("Evaluator_Connected" if ok else "Evaluator_Disconnected"))
            self.evaluator_link.start()

        send_marker("Screen_Setup")

    def get_current_scenario(self):
        if state.current_condition == "training":
            return "baseline"
        return state.current_condition

    def setup_finished_callback(self):
        if state.current_condition == "training":
            state.training_sequence = build_training_sequence()
            self.tutorial_screen.reset()
            self.stacked_widget.setCurrentIndex(1)
            self.tutorial_screen.setFocus()
        else:
            self.start_screen.configure_for_condition(state.current_condition)
            self.stacked_widget.setCurrentIndex(2)

    def tutorial_finished_callback(self):
        self.start_screen.configure_for_condition("training")
        self.stacked_widget.setCurrentIndex(2)

    def start_experiment_tracking(self):
        send_marker(f"Condition_Start_{state.current_condition}")
        if state.current_condition != "training":
            self.announce_scenario()

        rounds = TRAINING_ROUNDS if state.current_condition == "training" else MAX_ROUNDS_PER_CONDITION
        self.stacked_widget.setCurrentIndex(3)
        self.dual_task_screen.start_condition_session(max_rounds=rounds)
        self.dual_task_screen.setFocus()

    def announce_scenario(self):
        mode = self.get_current_scenario()
        send_marker(f"Scenario_Changed_{mode}")
        set_robot_speed(mode)

        if mode == "audio":
            audio_sys.play_researcher(mode_audio_only)
        elif mode == "haptic":
            audio_sys.play_researcher(mode_haptic_only)
        elif mode == "audio_haptic":
            audio_sys.play_researcher(mode_audio_haptic)
        elif mode == "robot_fast":
            audio_sys.play_researcher(mode_robot_fast)
        elif mode == "robot_slow":
            audio_sys.play_researcher(mode_robot_slow)
        elif mode == "baseline":
            audio_sys.play_researcher(mode_baseline)

    def trigger_mistake(self):
        if self.mistake_on_cooldown or state.difficulty != "hard":
            return

        send_marker("Manual_Mistake_Alert_Triggered")
        mode = self.get_current_scenario()

        if mode in ["haptic", "audio_haptic"]:
            activate_haptic_vest()
        if mode in ["audio", "audio_haptic"]:
            audio_sys.play_both(mistake_audio)

        self.mistake_on_cooldown = True
        QTimer.singleShot(2000, self.reset_mistake_cooldown)

    def reset_mistake_cooldown(self):
        self.mistake_on_cooldown = False

    def on_point_button(self, point: int):
        current_w = self.stacked_widget.currentWidget()
        if current_w is self.tutorial_screen:
            self.tutorial_screen.on_point_key(point)
        elif current_w is self.dual_task_screen:
            self.dual_task_screen.handover_received(point)

    def on_handover_complete(self, point_pressed: int):
        send_point_to_robot(point_pressed)

    def on_condition_complete(self, final_score: int):
        audio_sys.stop_looping_alarm()
        send_marker(f"Condition_Complete_{state.current_condition}_FinalScore_{final_score}")
        self.stacked_widget.setCurrentIndex(4)
        self.scoreboard_screen.start_scoreboard(state.current_condition, final_score)
        self.scoreboard_screen.setFocus()

    def return_to_setup(self):
        send_marker("Returned_To_Main_Menu")
        self.stacked_widget.setCurrentIndex(0)
