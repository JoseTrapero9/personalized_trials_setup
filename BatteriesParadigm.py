import sys
import random
import os
import csv
import time
import math
import subprocess
import threading
import asyncio
import socket
import bhaptics_python
import sounddevice as sd
import soundfile as sf

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, 
                             QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QStackedWidget,
                             QShortcut, QComboBox, QGridLayout, QCheckBox, QGroupBox, QFrame,
                             QListWidget, QAbstractItemView, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence, QPixmap
from pylsl import StreamInfo, StreamOutlet

base_dir = os.path.dirname(os.path.abspath(__file__))
audio_dir = os.path.join(base_dir, "audios")

correct_audio = os.path.join(audio_dir, "correct_answer.wav") 
incorrect_audio = os.path.join(audio_dir, "incorrect_answer.wav")
alarm_audio = os.path.join(audio_dir, "alarm_llm.wav")

if not os.path.exists(alarm_audio):
    alarm_audio = incorrect_audio

mode_audio_haptic = os.path.join(audio_dir, "AUDIO_HAPTIC_MODE.wav")
mode_audio_only = os.path.join(audio_dir, "AUDIOHELP_mode.wav")
mode_haptic_only = os.path.join(audio_dir, "HapticVest_Mode.wav")
mode_robot_fast = os.path.join(audio_dir, "ROBOT_FAST_MODE.wav")
mode_robot_slow = os.path.join(audio_dir, "ROBOT_SLOW_MODE.wav")
mode_baseline = os.path.join(audio_dir, "BASELINE_MODE.wav")

container1_audio = os.path.join(audio_dir, "CONTAINER1_ALERT.wav")
container2_audio = os.path.join(audio_dir, "CONTAINER2.wav")
mistake_audio = os.path.join(audio_dir, "MISTAKE_ALERT.wav")

ROBOT_OWN_IP = "192.168.29.61"
DIFFICULTY_PORT = 50001

marker_outlet = None
controller = None

def init_lsl():
    global marker_outlet
    info = StreamInfo('ParadigmMarkers', 'Markers', 1, 0, 'string', 'pyqt_paradigm_123')
    marker_outlet = StreamOutlet(info)
    print("LSL Marker Outlet initialized.")

def send_marker(marker_string):
    global marker_outlet
    if marker_outlet is not None:
        marker_outlet.push_sample([marker_string])
        print(f"Sent marker: {marker_string}")

def set_robot_speed(scenario_name):
    level = 1
    if scenario_name == "robot_slow":
        level = 0
    elif scenario_name == "robot_fast":
        level = 2
        
    def send_level():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect((ROBOT_OWN_IP, DIFFICULTY_PORT))
            sock.sendall(str(level).encode('utf-8'))
            sock.close()
            print(f"Robot speed set to Level {level} for '{scenario_name}'")
        except Exception:
            pass
            
    threading.Thread(target=send_level, daemon=True).start()

class AudioController:
    def __init__(self):
        self.participant_device = None
        self.researcher_device = None
        self.alarm_active = False
        
    def setup_devices(self, participant_keyword, researcher_keyword):
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d['max_output_channels'] > 0:
                name = d['name'].lower()
                if participant_keyword.lower() in name and self.participant_device is None:
                    self.participant_device = i
                    print(f"Participant Audio set to Device {i}: {d['name']}")
                elif researcher_keyword.lower() in name and self.researcher_device is None:
                    self.researcher_device = i
                    print(f"Researcher Audio set to Device {i}: {d['name']}")

    def play_participant(self, filepath):
        if os.path.exists(filepath):
            threading.Thread(target=self._play_audio, args=(filepath, self.participant_device), daemon=True).start()

    def play_researcher(self, filepath):
        if os.path.exists(filepath):
            threading.Thread(target=self._play_audio, args=(filepath, self.researcher_device), daemon=True).start()

    def _play_audio(self, filepath, device_id):
        try:
            data, fs = sf.read(filepath, dtype='float32')
            sd.play(data, samplerate=fs, device=device_id)
            sd.wait() 
        except Exception as e:
            print(f"Error playing {filepath}: {e}")

    def start_looping_alarm(self, filepath):
        if self.alarm_active or not os.path.exists(filepath):
            return
        self.alarm_active = True
        threading.Thread(target=self._loop_worker, args=(filepath, self.participant_device), daemon=True).start()

    def stop_looping_alarm(self):
        self.alarm_active = False
        sd.stop()

    def _loop_worker(self, filepath, device_id):
        try:
            data, fs = sf.read(filepath, dtype='float32')
            while self.alarm_active:
                sd.play(data, samplerate=fs, device=device_id)
                sd.wait()
        except Exception as e:
            print(f"Alarm loop error: {e}")

audio_sys = AudioController()
haptic_loop = None

async def init_haptics():
    app_id = "6a97da355fa17dce7a1e0d7b"
    api_key = "LsHVhykpVUDmGRxVY0FB"
    await bhaptics_python.registry_and_initialize(app_id, api_key, "")
    print("bHaptics background connection established.")

async def trigger_vest_async():
    full_vest_pattern = [0] * 20 + [50] * 20
    await bhaptics_python.play_dot(0, 500, full_vest_pattern)
    
async def close_haptics():
    await bhaptics_python.stop_all()
    await bhaptics_python.close()
    print("bHaptics background connection closed.")

def start_haptic_thread():
    global haptic_loop
    haptic_loop = asyncio.new_event_loop()
    t = threading.Thread(target=haptic_loop.run_forever, daemon=True)
    t.start()
    asyncio.run_coroutine_threadsafe(init_haptics(), haptic_loop)

def activate_haptic_vest():
    if haptic_loop is not None:
        asyncio.run_coroutine_threadsafe(trigger_vest_async(), haptic_loop)

font_size_multiplier = 1.8
difficulty = "hard"
subject_number = "1"
current_condition = "training"
active_scenarios_list = []
robot_process = None

def load_synch_sequence(path=os.path.join(base_dir, "log_files", "s14_no_llm_sequence.txt")):
    sequence = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                if row["mode"] == "image":
                    sequence.append(("image", row["param1"], None))
                else:
                    sequence.append(("text", int(row["param1"]), row["param2"]))
    else:
        # fallback sequence if file is missing
        for i in range(1, 41):
            sequence.append(("text", random.choice([6, 7, 8, 9]), "Assemble accordingly"))
    return sequence

WORKPIECE_SEQUENCE = load_synch_sequence()

class setupscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(20 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(16 * font_size_multiplier))
        title_font = QFont("Helvetica", int(18 * font_size_multiplier), QFont.Bold)
        
        self.title_label = QLabel("Experiment Configuration")
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)
        
        self.subj_label = QLabel("Subject Number:")
        self.subj_label.setFont(main_font)
        layout.addWidget(self.subj_label, alignment=Qt.AlignCenter)
        
        self.subj_combo = QComboBox()
        self.subj_combo.setFont(main_font)
        self.subj_combo.setFixedWidth(int(300 * font_size_multiplier))
        for i in range(1, 100):
            self.subj_combo.addItem(str(i))
        layout.addWidget(self.subj_combo, alignment=Qt.AlignCenter)
        
        self.cond_label = QLabel("Condition:")
        self.cond_label.setFont(main_font)
        layout.addWidget(self.cond_label, alignment=Qt.AlignCenter)
        
        self.cond_combo = QComboBox()
        self.cond_combo.setFont(main_font)
        self.cond_combo.setFixedWidth(int(300 * font_size_multiplier))
        self.cond_combo.addItems(["training", "baseline", "easy", "hard", "manual"])
        self.cond_combo.currentTextChanged.connect(self.on_condition_changed)
        layout.addWidget(self.cond_combo, alignment=Qt.AlignCenter)
        
        # scenario selection and ordering group
        self.scenario_group = QGroupBox("Order Scenarios (Drag & Drop, Check to Include)")
        self.scenario_group.setFont(main_font)
        group_layout = QVBoxLayout()

        self.scenario_list_widget = QListWidget()
        self.scenario_list_widget.setFont(main_font)
        self.scenario_list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.scenario_list_widget.setDefaultDropAction(Qt.MoveAction)
        self.scenario_list_widget.setFixedWidth(int(380 * font_size_multiplier))
        self.scenario_list_widget.setFixedHeight(int(180 * font_size_multiplier))

        scenarios = ["audio", "haptic", "audio_haptic", "robot_fast", "robot_slow", "baseline"]
        for sc in scenarios:
            item = QListWidgetItem(sc)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked)
            self.scenario_list_widget.addItem(item)

        group_layout.addWidget(self.scenario_list_widget)
        self.scenario_group.setLayout(group_layout)
        self.scenario_group.setEnabled(False)
        layout.addWidget(self.scenario_group, alignment=Qt.AlignCenter)
        
        self.continue_button = QPushButton("Continue")
        self.continue_button.setFont(main_font)
        self.continue_button.setFixedWidth(int(300 * font_size_multiplier))
        self.continue_button.setFixedHeight(int(60 * font_size_multiplier))
        self.continue_button.clicked.connect(self.save_and_continue)
        layout.addWidget(self.continue_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def on_condition_changed(self, text):
        self.scenario_group.setEnabled(text == "manual")
        
    def save_and_continue(self):
        global difficulty, subject_number, current_condition, active_scenarios_list
        
        subject_number = self.subj_combo.currentText()
        current_condition = self.cond_combo.currentText()
        
        if current_condition == "hard":
            difficulty = "hard"
            active_scenarios_list = ["audio", "haptic", "audio_haptic", "robot_fast", "robot_slow", "baseline"]
        elif current_condition == "manual":
            difficulty = "hard"
            active_scenarios_list = []
            for i in range(self.scenario_list_widget.count()):
                item = self.scenario_list_widget.item(i)
                if item.checkState() == Qt.Checked:
                    active_scenarios_list.append(item.text())
            if not active_scenarios_list:
                QMessageBox.warning(self, "Error", "Please select at least one scenario in manual mode.")
                return
        else:
            difficulty = "easy"
            active_scenarios_list = ["baseline"]
            
        send_marker(f"Setup_Complete_Subj_{subject_number}_Cond_{current_condition}")
        self.switch_callback()

class startscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.ticks_left = 20
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(30 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(20 * font_size_multiplier))
        button_font = QFont("Helvetica", int(18 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(48 * font_size_multiplier), QFont.Bold)
        
        intro_text = ("<b>Paradigm Start</b><br><br>"
                      "1. Retrieve parts from Container I or II.<br>"
                      "2. Observe the objective and assemble according to color and slot rules.<br>"
                      "3. You have <b>25 seconds</b> before the alarm triggers.<br><br>"
                      "Click the <b>Submit</b> button upon completion.")
        
        self.message_label = QLabel(intro_text)
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        
        self.countdown_label = QLabel("")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.hide()
        layout.addWidget(self.countdown_label)

        self.start_button = QPushButton("Start Paradigm")
        self.start_button.setFont(button_font)
        self.start_button.setFixedWidth(int(300 * font_size_multiplier))
        self.start_button.setFixedHeight(int(70 * font_size_multiplier))
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def on_start_clicked(self):
        global robot_process
        send_marker("Robot_Started_Waiting")
        
        robot_process = subprocess.Popen(
            [sys.executable, "robot_sequence.py"],
            stdin=subprocess.PIPE,
            text=True
        )
        
        self.start_button.hide()
        self.message_label.setText("Preparing experimental components...")
        self.countdown_label.setText(f"{self.ticks_left} s")
        self.countdown_label.show()
        self.timer.start(1000)
        
    def timer_tick(self):
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.timer.stop()
            self.switch_callback()
        else:
            self.countdown_label.setText(f"{self.ticks_left} s")

class restscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.ticks_left = 30
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(40 * font_size_multiplier))
        main_font = QFont("Helvetica", int(24 * font_size_multiplier), QFont.Bold)
        timer_font = QFont("Helvetica", int(60 * font_size_multiplier), QFont.Bold)
        
        self.message_label = QLabel("Great job! Take a short break.<br><br>The next scenario will start soon.")
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        self.countdown_label = QLabel("20 s")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.countdown_label)
        self.setLayout(layout)
        
    def start_rest(self):
        send_marker("Screen_Short_Rest_Started")
        self.ticks_left = 20
        self.countdown_label.setText(f"{self.ticks_left} s")
        self.timer.start(1000)
        
    def timer_tick(self):
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.timer.stop()
            send_marker("Screen_Short_Rest_Finished")
            self.switch_callback()
        else:
            self.countdown_label.setText(f"{self.ticks_left} s")

class longrestscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(40 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(24 * font_size_multiplier), QFont.Bold)
        button_font = QFont("Helvetica", int(18 * font_size_multiplier))
        
        self.message_label = QLabel("You have completed a block of 3 scenarios.<br><br>Please take a longer break.<br>Press the button when you are ready to continue.")
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        self.resume_button = QPushButton("Continue Measurements")
        self.resume_button.setFont(button_font)
        self.resume_button.setFixedWidth(int(400 * font_size_multiplier))
        self.resume_button.setFixedHeight(int(80 * font_size_multiplier))
        self.resume_button.clicked.connect(self.on_resume_clicked)
        layout.addWidget(self.resume_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def start_rest(self):
        send_marker("Screen_Long_Variable_Rest_Started")
        
    def on_resume_clicked(self):
        send_marker("Screen_Long_Variable_Rest_Finished")
        self.switch_callback()

class retrievalscreen(QWidget):
    def __init__(self, finish_callback, get_scenario_cb):
        super().__init__()
        self.finish_callback = finish_callback
        self.get_scenario_cb = get_scenario_cb
        self.ticks_left = 25
        self.container_toggle = True
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(30 * font_size_multiplier))

        main_font = QFont("Helvetica", int(22 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(55 * font_size_multiplier), QFont.Bold)

        self.instruction_label = QLabel("")
        self.instruction_label.setFont(main_font)
        self.instruction_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.instruction_label)

        self.timer_label = QLabel("25 s")
        self.timer_label.setFont(timer_font)
        self.timer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.timer_label)

        self.setLayout(layout)

    def start_retrieval(self):
        self.ticks_left = 20
        target_container = "I" if self.container_toggle else "II"
        self.instruction_label.setText(f"Retrieve the parts from <b>Container {target_container}</b>")
        self.timer_label.setText(f"{self.ticks_left} s")

        current_scenario = self.get_scenario_cb()
        send_marker(f"Retrieval_Start_Container_{target_container}")

        if difficulty == "hard" and current_scenario in ["audio", "audio_haptic"]:
            audio_sys.play_participant(container1_audio if self.container_toggle else container2_audio)
        elif difficulty != "hard":
            audio_sys.play_participant(container1_audio if self.container_toggle else container2_audio)

        self.container_toggle = not self.container_toggle
        self.timer.start(1000)

    def timer_tick(self):
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.timer.stop()
            send_marker("Retrieval_Finished")
            self.finish_callback()
        else:
            self.timer_label.setText(f"{self.ticks_left} s")

class workpiecetaskscreen(QWidget):
    def __init__(self, finish_callback, get_scenario_cb):
        super().__init__()
        self.finish_callback = finish_callback
        self.get_scenario_cb = get_scenario_cb
        
        self.ticks_left = 25
        self.alarm_triggered = False
        self.active_collection_pt = None
        self.task_start_time = 0.0
        self.current_task_info = ""
        self.warn_visible = False
        
        # evaluation tracking per workpiece
        self.current_trial_num = 0
        self.evaluated = False
        self.assembly_status = "none"
        self.pending_log = None

        # main 1-second countdown timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        
        # 500 ms timer for blinking warning text
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self.toggle_warning_blink)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setSpacing(int(20 * font_size_multiplier))
        
        # left panel
        self.left_panel = QFrame()
        self.left_panel.setFrameShape(QFrame.StyledPanel)
        self.left_panel.setStyleSheet("background-color: white; border-radius: 8px;")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setAlignment(Qt.AlignCenter)
        left_layout.setSpacing(int(15 * font_size_multiplier))

        title_font = QFont("Helvetica", int(22 * font_size_multiplier), QFont.Bold)
        body_font = QFont("Helvetica", int(18 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(48 * font_size_multiplier), QFont.Bold)
        warn_font = QFont("Helvetica", int(24 * font_size_multiplier), QFont.Bold)
        submit_btn_font = QFont("Helvetica", int(20 * font_size_multiplier), QFont.Bold)

        self.header_label = QLabel("CURRENT WORKPIECE")
        self.header_label.setFont(title_font)
        left_layout.addWidget(self.header_label, alignment=Qt.AlignCenter)

        self.timer_label = QLabel("25 s")
        self.timer_label.setFont(timer_font)
        left_layout.addWidget(self.timer_label, alignment=Qt.AlignCenter)

        # blinking warning label
        self.warning_label = QLabel("")
        self.warning_label.setFont(warn_font)
        self.warning_label.setStyleSheet("color: red;")
        self.warning_label.setFixedHeight(int(35 * font_size_multiplier))
        self.warning_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.warning_label, alignment=Qt.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.image_label, alignment=Qt.AlignCenter)

        self.instruction_label = QLabel()
        self.instruction_label.setFont(title_font)
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.instruction_label.setWordWrap(True)
        left_layout.addWidget(self.instruction_label, alignment=Qt.AlignCenter)

        self.handover_label = QLabel()
        self.handover_label.setFont(body_font)
        self.handover_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.handover_label, alignment=Qt.AlignCenter)

        # submit button for participant
        self.submit_button = QPushButton("Submit")
        self.submit_button.setFont(submit_btn_font)
        self.submit_button.setFixedWidth(int(250 * font_size_multiplier))
        self.submit_button.setFixedHeight(int(70 * font_size_multiplier))
        self.submit_button.clicked.connect(self.on_submit_clicked)
        left_layout.addWidget(self.submit_button, alignment=Qt.AlignCenter)

        # right panel
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.StyledPanel)
        self.right_panel.setStyleSheet("background-color: #FAFAFA; border-radius: 8px;")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setAlignment(Qt.AlignTop)
        right_layout.setSpacing(int(10 * font_size_multiplier))

        rules_head = QLabel("Rules")
        rules_head.setFont(title_font)
        right_layout.addWidget(rules_head)

        rules_colors = QLabel(
            "<b>Colors:</b><br>"
            "<font color='blue'>Blue:</font> 1<br>"
            "<font color='red'>Red:</font> 2<br>"
            "<font color='#B8860B'>Yellow:</font> 3<br>"
            "<font color='green'>Green:</font> 4<br><br>"
            "<b>Slots:</b><br>"
            "Slot 1 = x 1<br>"
            "Slot 2 = x 2<br>"
            "Slot 3 = x 3"
        )
        rules_colors.setFont(body_font)
        right_layout.addWidget(rules_colors)

        main_layout.addWidget(self.left_panel, 3)
        main_layout.addWidget(self.right_panel, 1)
        self.setLayout(main_layout)

    def start_task(self, trial_num, target_pt):
        # flush any unwritten pending log from the previous trial
        self.flush_pending_log()

        scenario = self.get_scenario_cb()
        if scenario == "robot_fast":
            self.ticks_left = 20
        elif scenario == "robot_slow":
            self.ticks_left = 30
        else:
            self.ticks_left = 25

        self.current_trial_num = trial_num
        self.evaluated = False
        self.assembly_status = "none"
        self.pending_log = None

        self.alarm_triggered = False
        self.active_collection_pt = target_pt
        self.task_start_time = time.perf_counter()
        self.warn_visible = False

        idx = (trial_num - 1) % len(WORKPIECE_SEQUENCE)
        mode, p1, p2 = WORKPIECE_SEQUENCE[idx]

        if mode == "image":
            self.instruction_label.setText("")
            self.current_task_info = f"image_{p1}"
            img_path = os.path.join(base_dir, "workpieces", p1)
            if os.path.exists(img_path):
                pixmap = QPixmap(img_path)
                self.image_label.setPixmap(pixmap.scaledToWidth(int(320 * font_size_multiplier), Qt.SmoothTransformation))
            else:
                self.image_label.setText(f"[Image: {p1}]")
        else:
            self.image_label.clear()
            self.current_task_info = f"sum_{p1}_{p2}"
            self.instruction_label.setText(f"Sum must be {p1}\n{p2}")

        pt_name = "Point 1 (Left)" if target_pt == 1 else "Point 2 (Right)"

        self.handover_label.setText(
            f"Place the workpiece at <b>{pt_name}</b>.<br>"
            f"Click <b>Submit</b> upon completion."
        )

        self.timer_label.setStyleSheet("color: black;")
        self.timer_label.setText(f"{self.ticks_left} s")
        self.warning_label.setText("")
        self.blink_timer.stop()
        
        send_marker(f"Workpiece_Task_Started_Trial_{trial_num}_Type_{self.current_task_info}")
        self.timer.start(1000)

    def record_evaluation(self, is_correct):
        # allow evaluation once per piece either during the task or in subsequent transitions
        if self.current_trial_num == 0 or self.evaluated:
            return

        self.evaluated = True
        self.assembly_status = "correct" if is_correct else "incorrect"
        send_marker(f"Assembly_Evaluated_{self.assembly_status}")

        # if task was already submitted, update and write the pending log immediately
        if self.pending_log is not None:
            self.pending_log["assembly_status"] = self.assembly_status
            self._write_csv_row(self.pending_log)
            self.pending_log = None

    def on_submit_clicked(self):
        if self.active_collection_pt is not None:
            self.handover_received(self.active_collection_pt)

    def toggle_warning_blink(self):
        self.warn_visible = not self.warn_visible
        self.warning_label.setText("WARNING - FINISH" if self.warn_visible else "")

    def timer_tick(self):
        self.ticks_left -= 1
        
        # switch to red and start blinking in the last 10 seconds
        if 0 < self.ticks_left <= 10:
            self.timer_label.setStyleSheet("color: red;")
            if not self.blink_timer.isActive():
                self.warn_visible = True
                self.warning_label.setText("WARNING - FINISH")
                self.blink_timer.start(250)
        
        if self.ticks_left <= 0:
            self.timer_label.setText("0 s")
            self.timer_label.setStyleSheet("color: red;")
            self.blink_timer.stop()
            self.warning_label.setText("WARNING - FINISH")
            
            if not self.alarm_triggered:
                self.alarm_triggered = True
                send_marker("Workpiece_Task_Overtime_Alarm_Started")
                audio_sys.start_looping_alarm(alarm_audio)
        else:
            self.timer_label.setText(f"{self.ticks_left} s")

    def handover_received(self, point_pressed):
        if self.active_collection_pt is None:
            return

        self.timer.stop()
        self.blink_timer.stop()
        self.warning_label.setText("")
        
        elapsed = time.perf_counter() - self.task_start_time

        if self.alarm_triggered:
            audio_sys.stop_looping_alarm()
            send_marker("Workpiece_Task_Overtime_Alarm_Stopped")

        send_marker(f"Handover_Confirmed_Point_{point_pressed}_Duration_{round(elapsed, 3)}")
        
        log_data = {
            "task_info": self.current_task_info,
            "elapsed": elapsed,
            "point_pressed": point_pressed,
            "alarm_triggered": self.alarm_triggered,
            "assembly_status": self.assembly_status
        }

        # if observer already pressed y or c during the task, write log immediately
        if self.evaluated:
            self._write_csv_row(log_data)
            self.pending_log = None
        else:
            # hold pending log to allow observer to evaluate during retrieval/rest
            self.pending_log = log_data
        
        self.active_collection_pt = None
        self.finish_callback(point_pressed)

    def flush_pending_log(self):
        if self.pending_log is not None:
            self._write_csv_row(self.pending_log)
            self.pending_log = None

    def _write_csv_row(self, log_dict):
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        try:
            subj_int = int(subject_number)
            subj_str = f"s{subj_int:02d}"
        except ValueError:
            subj_str = f"s_{subject_number}"
            
        filename = f"{subj_str}_{current_condition}.csv"
        filepath = os.path.join(log_dir, filename)
        file_exists = os.path.isfile(filepath)
        
        with open(filepath, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["subject", "condition", "difficulty", "task_info", "time_taken_s", "handover_point", "overtime_alarm", "assembly_status"])
            writer.writerow([
                subject_number,
                current_condition,
                difficulty,
                log_dict["task_info"],
                round(log_dict["elapsed"], 3),
                log_dict["point_pressed"],
                log_dict["alarm_triggered"],
                log_dict["assembly_status"]
            ])


class paradigmcontroller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Assembly and Collaboration Paradigm")
        self.current_trial = 0
        self.max_trials = 40
        
        self.scenarios = []
        self.current_scenario_idx = 0
        self.scenario_active_seconds = 0
        
        self.mistake_on_cooldown = False
        self.pending_short_rest = False
        self.pending_long_rest = False
        
        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.master_timer_tick)
        
        self.stacked_widget = QStackedWidget()
        self.setup_screen = setupscreen(self.setup_finished_callback)
        self.start_screen = startscreen(self.start_experiment_tracking) 
        self.retrieval_screen = retrievalscreen(self.show_workpiece_task, self.get_current_scenario)
        self.task_screen = workpiecetaskscreen(self.on_handover_complete, self.get_current_scenario)
        self.short_rest_screen = restscreen(self.after_rest_callback)
        self.long_rest_screen = longrestscreen(self.after_rest_callback)
        
        self.stacked_widget.addWidget(self.setup_screen)        # 0
        self.stacked_widget.addWidget(self.start_screen)        # 1
        self.stacked_widget.addWidget(self.retrieval_screen)    # 2
        self.stacked_widget.addWidget(self.task_screen)         # 3
        self.stacked_widget.addWidget(self.short_rest_screen)   # 4
        self.stacked_widget.addWidget(self.long_rest_screen)    # 5
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)
        
        self.quit_shortcut = QShortcut(QKeySequence("q"), self)
        self.quit_shortcut.activated.connect(QApplication.instance().quit)
        
        self.mistake_shortcut = QShortcut(QKeySequence("F12"), self)
        self.mistake_shortcut.activated.connect(self.trigger_mistake)

        # global shortcuts across all screens for observer evaluation
        self.y_shortcut = QShortcut(QKeySequence("y"), self)
        self.y_shortcut.activated.connect(lambda: self.task_screen.record_evaluation(True))

        self.c_shortcut = QShortcut(QKeySequence("c"), self)
        self.c_shortcut.activated.connect(lambda: self.task_screen.record_evaluation(False))

        send_marker("Screen_Setup")
        
    def setup_finished_callback(self):
        self.scenarios = active_scenarios_list.copy()
        if current_condition != "manual":
            random.shuffle(self.scenarios)
        
        print("\n" + "="*50)
        print("SCENARIO ORDER:")
        for i, s in enumerate(self.scenarios):
            print(f"  {i+1}. {s.upper()}")
        print("="*50 + "\n")
        
        self.stacked_widget.setCurrentIndex(1)
        
    def get_current_scenario(self):
        if self.scenarios and self.current_scenario_idx < len(self.scenarios):
            return self.scenarios[self.current_scenario_idx]
        return "baseline"
        
    def start_experiment_tracking(self):
        send_marker("Screen_Start_Instructions")
        if difficulty == "hard":
            self.scenario_active_seconds = 0
            self.master_timer.start(1000) 
            self.announce_scenario()
        self.start_trial_cycle()

    def master_timer_tick(self):
        self.scenario_active_seconds += 1
        if self.scenario_active_seconds >= 300:
            if self.current_scenario_idx + 1 >= len(self.scenarios):
                send_marker("Experiment_Complete_Time_Limit")
                QApplication.instance().quit()
            else:
                if (self.current_scenario_idx + 1) % 3 == 0:
                    self.pending_long_rest = True
                else:
                    self.pending_short_rest = True

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
        if self.mistake_on_cooldown or difficulty != "hard":
            return
            
        send_marker("Manual_Mistake_Alert_Triggered")
        mode = self.get_current_scenario()
        
        if mode in ["haptic", "audio_haptic"]:
            activate_haptic_vest()
        if mode in ["audio", "audio_haptic"]:
            audio_sys.play_participant(mistake_audio)
            
        self.mistake_on_cooldown = True
        QTimer.singleShot(2000, self.reset_mistake_cooldown)

    def reset_mistake_cooldown(self):
        self.mistake_on_cooldown = False

    def start_trial_cycle(self):
        if difficulty == "hard":
            if self.pending_long_rest:
                self.pending_long_rest = False
                self.master_timer.stop()
                self.long_rest_screen.start_rest()
                self.stacked_widget.setCurrentIndex(5)
                return
            elif self.pending_short_rest:
                self.pending_short_rest = False
                self.master_timer.stop()
                self.short_rest_screen.start_rest()
                self.stacked_widget.setCurrentIndex(4)
                return

        if difficulty != "hard" and self.current_trial >= self.max_trials:
            send_marker("Experiment_Complete_Trial_Limit")
            QApplication.instance().quit()
            return
            
        self.current_trial += 1
        send_marker(f"Screen_Trial_Cycle_{self.current_trial}_Start")

        self.retrieval_screen.start_retrieval()
        self.stacked_widget.setCurrentIndex(2)

    def show_workpiece_task(self):
        target_pt = 1 if (self.current_trial % 2 != 0) else 2
        self.task_screen.start_task(self.current_trial, target_pt)
        self.stacked_widget.setCurrentIndex(3)

    def on_handover_complete(self, point_pressed):
        global robot_process
        if robot_process is not None and robot_process.poll() is None:
            try:
                robot_process.stdin.write(f"{point_pressed}\n")
                robot_process.stdin.flush()
            except Exception:
                pass
        self.start_trial_cycle()

    def after_rest_callback(self):
        self.current_scenario_idx += 1
        self.scenario_active_seconds = 0
        self.announce_scenario()
        
        self.master_timer.start(1000)
        self.start_trial_cycle()

def cleanup_resources():
    global robot_process, controller
    send_marker("Application_Closing")
    
    if controller is not None:
        controller.task_screen.flush_pending_log()

    if robot_process is not None:
        robot_process.terminate()
        
    if haptic_loop is not None:
        future = asyncio.run_coroutine_threadsafe(close_haptics(), haptic_loop)
        try:
            future.result(timeout=2)
        except Exception:
            pass
        haptic_loop.call_soon_threadsafe(haptic_loop.stop)

def run_paradigm():
    global controller
    init_lsl()
    start_haptic_thread()
    
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_resources)
    
    audio_sys.setup_devices(participant_keyword="Realtek", researcher_keyword="Realtek")
    
    controller = paradigmcontroller()
    
    screens = app.screens()
    if len(screens) > 1:
        second_screen = screens[1].geometry()
        controller.move(second_screen.left(), second_screen.top())
        
    controller.showFullScreen()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_paradigm()
 