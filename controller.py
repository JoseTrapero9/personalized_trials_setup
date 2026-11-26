"""Main window: owns the screens and routes between them."""

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication, QMessageBox, QShortcut, QStackedWidget, QVBoxLayout, QWidget

from audio import audio_sys
from config import (
    MAX_ROUNDS_PER_CONDITION,
    TRAINING_CONDITIONS,
    TRAINING_ROUNDS,
    USE_REMOTE_EVALUATOR,
    get_cue_audio_paths,
    mode_audio_haptic,
    mode_audio_only,
    mode_baseline,
    mode_haptic_only,
)
from evaluator_link import EvaluatorLink
from feedback_cues import channels_for, play_feedback
from haptics import activate_haptic_vest
from lsl_markers import send_marker
from questionnaires import QUESTIONNAIRE_CONDITIONS, missing_conditions
from robot import send_robot_command, set_robot_speed
from screens.dual_task_screen import DualTaskScreen
from screens.pretrain_screen import PretrainScreen
from screens.questionnaire_screen import QuestionnaireScreen
from screens.scoreboard_screen import ArcadeScoreboardScreen
from screens.setup_screen import setupscreen
from screens.start_screen import startscreen
from screens.training_menu_dialog import TRAINING_PARTS, TrainingMenuDialog
from screens.tutorial_screen import tutorialscreen
from screens.warmup_screen import BatteryWarmupScreen, RadioWarmupScreen
from sequences import build_training_sequence, load_training_sequence
from state import state


class paradigmcontroller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dual-Task Assembly and Collaboration Paradigm")
        self.mistake_on_cooldown = False
        self._training_tasks = []
        self.training_plan = []
        self.last_training_score = None
        self.evaluator_connected = False

        self.stacked_widget = QStackedWidget()
        self.setup_screen = setupscreen(self.setup_finished_callback, self.start_sus_questionnaire,
                                        self.start_pretrain)
        self.tutorial_screen = tutorialscreen(self.tutorial_finished_callback, demo_callback=self.play_demo_cue)
        self.start_screen = startscreen(self.start_experiment_tracking)
        self.dual_task_screen = DualTaskScreen(
            round_complete_cb=self.on_handover_complete,
            condition_complete_cb=self.on_condition_complete,
            get_scenario_cb=self.get_current_scenario
        )
        self.scoreboard_screen = ArcadeScoreboardScreen(self.after_scoreboard)
        self.questionnaire_screen = QuestionnaireScreen()
        self.pretrain_screen = PretrainScreen()
        self.radio_warmup = RadioWarmupScreen(player_source=self.dual_task_screen.game_widget)
        self.battery_warmup = BatteryWarmupScreen()

        self.stacked_widget.addWidget(self.setup_screen)       # 0
        self.stacked_widget.addWidget(self.tutorial_screen)    # 1
        self.stacked_widget.addWidget(self.start_screen)       # 2
        self.stacked_widget.addWidget(self.dual_task_screen)   # 3
        self.stacked_widget.addWidget(self.scoreboard_screen)  # 4
        self.stacked_widget.addWidget(self.questionnaire_screen)  # 5
        self.stacked_widget.addWidget(self.pretrain_screen)       # 6
        self.stacked_widget.addWidget(self.radio_warmup)          # 7
        self.stacked_widget.addWidget(self.battery_warmup)        # 8

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)

        # Global Shortcuts
        # Ctrl+Q (not a single key) and always with a confirmation, also for Alt+F4 (closeEvent)
        self.quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut.activated.connect(self.close)

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
            self.evaluator_link.result_received.connect(self.dual_task_screen.remote_practice_result)
            self.evaluator_link.battery_received.connect(self.dual_task_screen.remote_battery_cue)
            self.evaluator_link.connection_changed.connect(self._evaluator_connection)
            self.evaluator_link.start()

        send_marker("Screen_Setup")

    # ------------------------------------------------------------------ safety
    def _evaluator_connection(self, ok):
        self.evaluator_connected = ok
        send_marker("Evaluator_Connected" if ok else "Evaluator_Disconnected")

    def closeEvent(self, event):
        answer = QMessageBox.question(
            self, "Quit the experiment?",
            "Quit the experiment program now?\n\nA running condition is stopped (the rounds so far are saved).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            send_marker("Quit_Confirmed")
            event.accept()
        else:
            send_marker("Quit_Cancelled")
            event.ignore()

    def preflight(self, kind, condition=""):
        """Researcher check before a run. True = start, False = back to the main menu."""
        import haptics
        import lsl_markers
        from audio import audio_sys
        from preflight import session_checks
        from screens.preflight_dialog import PreflightDialog

        def rows():
            return session_checks(
                kind, state.subject_number, condition, language=state.language, game_mode=state.game_mode,
                audio_cue_mode=state.audio_cue_mode, participant_device=audio_sys.participant_device,
                researcher_device=audio_sys.researcher_device, vest_connected=haptics.player.connected,
                vest_supported=haptics.WEBSOCKET_AVAILABLE, evaluator_connected=self.evaluator_connected,
                lsl_ok=lsl_markers.marker_outlet is not None, error_count=state.error_count)

        dialog = PreflightDialog("Check before starting", rows, self)
        ok = dialog.exec_() == PreflightDialog.Accepted
        levels = "_".join(f"{lv}{dialog.levels.count(lv)}" for lv in ("fail", "warn"))
        send_marker(f"Preflight_{'Start' if ok else 'Back'}_{kind}_{condition or 'none'}_{levels}")
        if not ok:
            self.return_to_setup()
        return ok

    def get_current_scenario(self):
        """Condition whose cues are used: in training, the condition of the current training block."""
        if state.current_condition == "training":
            return state.training_condition
        return state.current_condition

    def setup_finished_callback(self):
        if not self.preflight("training" if state.current_condition == "training" else "condition",
                              state.current_condition):
            return
        if state.current_condition == "training":
            menu = TrainingMenuDialog(self)                  # where to start (e.g. after a problem)
            if menu.exec_() != TrainingMenuDialog.Accepted:
                send_marker("Training_Menu_Back")
                self.return_to_setup()
                return
            start = menu.start_index
            self.training_plan = TRAINING_PARTS[start:start + 1] if menu.only_this else TRAINING_PARTS[start:]
            send_marker(f"Training_Plan_{'-'.join(self.training_plan)}")
            self._training_tasks = build_training_sequence(len(TRAINING_CONDITIONS) * TRAINING_ROUNDS)
            state.training_block = 0
            state.training_condition = TRAINING_CONDITIONS[0]
            self.next_training_part()
        else:
            self.start_screen.configure_for_condition(state.current_condition)
            self.stacked_widget.setCurrentIndex(2)

    def tutorial_finished_callback(self):
        """Task tutorial done: next training part (normally the radio warm-up)."""
        self.next_training_part()

    def next_training_part(self):
        """Runs the training parts chosen in the training menu, in order (TRAINING_PARTS)."""
        if not self.training_plan:
            self.finish_training()
            return
        part = self.training_plan.pop(0)
        send_marker(f"Training_Part_{part}")
        if part == "tutorial":
            self.tutorial_screen.reset()
            self.stacked_widget.setCurrentIndex(1)
            self.tutorial_screen.setFocus()
        elif part == "warmup_radio":
            self.stacked_widget.setCurrentIndex(7)
            self.radio_warmup.start(finish_cb=self.next_training_part)
        elif part == "warmup_battery":
            self.stacked_widget.setCurrentIndex(8)
            self.battery_warmup.start(finish_cb=self.next_training_part)
            self.battery_warmup.setFocus()
        else:
            self.show_training_block(int(part[5:]))

    def finish_training(self):
        """After the last chosen part: scoreboard if a block was played, else back to the menu."""
        if self.last_training_score is None:
            self.return_to_setup()
            return
        score, self.last_training_score = self.last_training_score, None
        self.stacked_widget.setCurrentIndex(4)
        self.scoreboard_screen.start_scoreboard("training", score)
        self.scoreboard_screen.setFocus()

    # ------------------------------------------------------------------ training blocks
    def show_training_block(self, index):
        """Cue slide of training block `index`, then its start screen. Blocks: TRAINING_CONDITIONS, in order."""
        state.training_block = index
        state.training_condition = TRAINING_CONDITIONS[index]
        seq, name = load_training_sequence(state.training_condition)   # log_files/training_<condition>.txt
        if seq:
            state.training_sequence, state.training_sequence_file = seq, name
        else:                                            # file missing: generated tasks, as before
            tasks = self._training_tasks
            start = index * TRAINING_ROUNDS              # every block gets its own battery tasks
            state.training_sequence = [tasks[(start + k) % len(tasks)] for k in range(TRAINING_ROUNDS)]
            state.training_sequence_file = ""
        self.tutorial_screen.show_cue_slide(state.training_condition, index, len(TRAINING_CONDITIONS),
                                            finish_cb=self._training_block_ready)
        self.stacked_widget.setCurrentIndex(1)
        self.tutorial_screen.setFocus()

    def _training_block_ready(self):
        self.start_screen.configure_for_condition("training")
        self.stacked_widget.setCurrentIndex(2)

    def play_demo_cue(self, condition, is_correct):
        """Sample cue on a training slide (keys 1 / 2): exactly the cue of that condition."""
        play_feedback(channels_for(condition), is_correct)

    def start_experiment_tracking(self):
        send_marker(f"Condition_Start_{state.current_condition}")
        if state.current_condition == "training":
            send_marker(f"Training_Block_Start_{state.training_block + 1}_{state.training_condition}")
        self.announce_scenario()
        self.robot_command("go 1")          # every condition and every training block starts at point 1

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
            _, neg_wav = get_cue_audio_paths(state.audio_cue_mode)
            audio_sys.play_both(neg_wav)

        self.mistake_on_cooldown = True
        QTimer.singleShot(2000, self.reset_mistake_cooldown)

    def reset_mistake_cooldown(self):
        self.mistake_on_cooldown = False

    def on_point_button(self, point: int):
        current_w = self.stacked_widget.currentWidget()
        if current_w is self.tutorial_screen:
            self.tutorial_screen.on_point_key(point)
        elif current_w is self.battery_warmup:
            self.battery_warmup.on_point_key(point)
        elif current_w is self.dual_task_screen:
            self.dual_task_screen.handover_received(point)

    def on_handover_complete(self, point_pressed: int, next_point=None):
        """Handover at point_pressed; next_point = point of the next round (None = last round: park)."""
        self.robot_command(str(point_pressed))
        self.robot_command(f"go {next_point}" if next_point else "home")

    def robot_command(self, command):
        sent = send_robot_command(command)
        send_marker(f"Robot_Command_{command.replace(' ', '_')}{'' if sent else '_NotRunning'}")

    def on_condition_complete(self, final_score: int):
        audio_sys.stop_looping_alarm()
        send_marker(f"Condition_Complete_{state.current_condition}_FinalScore_{final_score}")
        if state.current_condition == "training":
            send_marker(f"Training_Block_Complete_{state.training_block + 1}_{state.training_condition}"
                        f"_Score_{final_score}")
            self.last_training_score = final_score
            self.next_training_part()                    # next part, scoreboard after the last one
            return
        self.stacked_widget.setCurrentIndex(4)
        self.scoreboard_screen.start_scoreboard(state.current_condition, final_score)
        self.scoreboard_screen.setFocus()

    def after_scoreboard(self):
        """Scoreboard closed: NASA-TLX for the condition that just ended, then the main menu."""
        if state.current_condition not in QUESTIONNAIRE_CONDITIONS:      # training
            self.return_to_setup()
            return
        self.stacked_widget.setCurrentIndex(5)
        self.questionnaire_screen.start_nasatlx(
            state.subject_number, state.current_condition, state.language, state.game_mode,
            finish_cb=self.return_to_setup)

    def start_pretrain(self):
        """'pre-train' chosen in the condition menu: learn the cues, then back to the main menu."""
        if not self.preflight("pretrain"):
            return
        self.stacked_widget.setCurrentIndex(6)
        self.pretrain_screen.start(state.subject_number, state.language, state.audio_cue_mode,
                                   finish_cb=self.return_to_setup)

    def start_sus_questionnaire(self):
        """'sus' chosen in the condition menu: experience questionnaire for all conditions + summary files."""
        if not self.preflight("sus"):
            return
        missing = missing_conditions(state.subject_number, "nasatlx")
        if missing:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Missing conditions")
            box.setText(f"Subject {state.subject_number} has no NASA-TLX file for:\n\n"
                        f"    {', '.join(missing)}\n\n"
                        "These conditions were probably not run (or not finished).\n\n"
                        "Continue: do the questionnaire and create the subject files without them.\n"
                        "Go back: return to the main menu.")
            proceed = box.addButton("Continue", QMessageBox.AcceptRole)
            back = box.addButton("Go back", QMessageBox.RejectRole)
            box.setDefaultButton(back)
            box.setStyleSheet("QLabel { font-size: 20px; } QPushButton { font-size: 20px; padding: 8px 24px; }")
            box.exec_()
            if box.clickedButton() is not proceed:
                send_marker("SUS_Cancelled_Missing_Conditions")
                return
        self.stacked_widget.setCurrentIndex(5)
        self.questionnaire_screen.start_sus(state.subject_number, state.language, finish_cb=self.return_to_setup)

    def return_to_setup(self):
        self.radio_warmup.stop()
        self.training_plan, self.last_training_score = [], None
        send_marker("Returned_To_Main_Menu")
        self.stacked_widget.setCurrentIndex(0)
