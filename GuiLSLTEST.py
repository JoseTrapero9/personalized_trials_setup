# This code runs both the GUI and the robot sequence in a coordinated manner, 
# ensuring that the robot waits for user input before proceeding to the next step. 
# It also handles LSL marker streaming for synchronization with other systems.

import sys
import random
import os
import csv
import time
import math
import subprocess
import threading
import asyncio
import bhaptics_python
import sounddevice as sd
import soundfile as sf

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, 
                             QPushButton, QVBoxLayout, QMessageBox, QStackedWidget,
                             QShortcut, QComboBox, QGridLayout)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence
from pylsl import StreamInfo, StreamOutlet

# dynamically resolve the directory where this script is located
base_dir = os.path.dirname(os.path.abspath(__file__))

# All audio files are now set to .wav as requested
correct_audio = os.path.join(base_dir, "correct_answer.wav") 
incorrect_audio = os.path.join(base_dir, "incorrect_answer.wav")
mode_audio_haptic = os.path.join(base_dir, "AUDIO_HAPTIC_MODE.wav")
mode_audio_only = os.path.join(base_dir, "AUDIOHELP_mode.wav")
mode_haptic_only = os.path.join(base_dir, "HapticVest_Mode.wav")
container1_audio = os.path.join(base_dir, "CONTAINER1_ALERT.wav")
container2_audio = os.path.join(base_dir, "CONTAINER2.wav")
mistake_audio = os.path.join(base_dir, "MISTAKE_ALERT.wav")

# --- LSL Setup ---
marker_outlet = None

def init_lsl():
    global marker_outlet
    # Name, Type, Channel Count, Sampling Rate (0 = irregular), Data Format, Source ID
    info = StreamInfo('ParadigmMarkers', 'Markers', 1, 0, 'string', 'pyqt_paradigm_123')
    marker_outlet = StreamOutlet(info)
    print("LSL Marker Outlet initialized.")

def send_marker(marker_string):
    global marker_outlet
    if marker_outlet is not None:
        marker_outlet.push_sample([marker_string])
        print(f"Sent marker: {marker_string}")

# --- Audio Controller ---
class AudioController:
    def __init__(self):
        self.participant_device = None
        self.researcher_device = None
        
    def setup_devices(self, participant_keyword, researcher_keyword):
        # Query all available audio devices in Windows
        devices = sd.query_devices()
        
        for i, d in enumerate(devices):
            # Find output devices matching the keywords
            if d['max_output_channels'] > 0:
                name = d['name'].lower()
                if participant_keyword.lower() in name and self.participant_device is None:
                    self.participant_device = i
                    print(f"Participant Audio set to Device {i}: {d['name']}")
                elif researcher_keyword.lower() in name and self.researcher_device is None:
                    self.researcher_device = i
                    print(f"Researcher Audio set to Device {i}: {d['name']}")
                    
        if self.participant_device is None:
            print(f"WARNING: Could not find participant device containing '{participant_keyword}'")
        if self.researcher_device is None:
            print(f"WARNING: Could not find researcher device containing '{researcher_keyword}'")

    def play_participant(self, filepath):
        threading.Thread(target=self._play_audio, args=(filepath, self.participant_device), daemon=True).start()

    def play_researcher(self, filepath):
        threading.Thread(target=self._play_audio, args=(filepath, self.researcher_device), daemon=True).start()

    def _play_audio(self, filepath, device_id):
        try:
            # Added dtype='float32' to fix the "rushed" audio playback distortion
            data, fs = sf.read(filepath, dtype='float32')
            sd.play(data, samplerate=fs, device=device_id)
            sd.wait() # Keep thread alive until audio finishes playing
        except Exception as e:
            print(f"Error playing {filepath}: {e}")

audio_sys = AudioController()

# --- Mistake Alert / Haptic Setup ---
haptic_loop = None

async def init_haptics():
    # initialize the bhaptics sdk
    app_id = "3wpIajB4Bdq2KfRhkDzZ"
    api_key = "yimPxWeZlB2Hxk5dNbOZ"
    await bhaptics_python.registry_and_initialize(app_id, api_key, "")
    print("bHaptics background connection established.")

async def trigger_vest_async():
    # Create a list of 40 motors, all set to 50 intensity
    full_vest_pattern = [50] * 40
    # play the full pattern for 500ms
    await bhaptics_python.play_dot(0, 500, full_vest_pattern)
    
async def close_haptics():
    await bhaptics_python.stop_all()
    await bhaptics_python.close()
    print("bHaptics background connection closed.")

def start_haptic_thread():
    global haptic_loop
    # Create a dedicated event loop for the background thread
    haptic_loop = asyncio.new_event_loop()
    
    # Run the loop forever in a daemon thread
    t = threading.Thread(target=haptic_loop.run_forever, daemon=True)
    t.start()
    
    # Schedule the one-time bHaptics initialization
    asyncio.run_coroutine_threadsafe(init_haptics(), haptic_loop)

def activate_haptic_vest():
    # Safely send the trigger command to the background haptics loop
    if haptic_loop is not None:
        asyncio.run_coroutine_threadsafe(trigger_vest_async(), haptic_loop)


# set this multiplier to adjust the overall scaling of fonts and ui elements
font_size_multiplier = 1.6

# global variables for experiment configuration
difficulty = "hard"
subject_number = "1"
current_condition = "training"

# global reference to the robot process
robot_process = None

def get_equation_for_target(target, is_x=False):
    if difficulty == "easy":
        if is_x:
            # easy mode x coordinate: 2 numbers
            op = random.choice(["+", "-"])
            
            if op == "+" and target > 1:
                a = random.randint(1, target - 1)
                b = target - a
                return f"{a} + {b}"
            else:
                b = random.randint(1, 9)
                a = target + b
                return f"{a} - {b}"
        else:
            # easy mode y coordinate: original 3 numbers logic
            a = random.randint(1, 9)
            b = random.randint(1, 9)
            c = a + b - target
            
            while c < 1 or c > 9:
                a = random.randint(1, 9)
                b = random.randint(1, 9)
                c = a + b - target
                
            return f"{a} + {b} - {c}"
            
    elif difficulty == "hard":
        # hard mode: custom constraints per operation type
        equation_type = random.choice(["add_sub", "mul_sub", "div_sub"])
        
        if equation_type == "add_sub":
            a = random.randint(10, 39)
            b = random.randint(10, 39)
            c = a + b - target
            
            while c < 10 or c > 39:
                a = random.randint(10, 39)
                b = random.randint(10, 39)
                c = a + b - target
                
            return f"{a} + {b} - {c}"
            
        elif equation_type == "mul_sub":
            a = random.randint(3, 12)
            b = random.randint(3, 12)
            c = (a * b) - target
            
            while c < 0:
                a = random.randint(3, 12)
                b = random.randint(3, 12)
                c = (a * b) - target
                
            return f"({a} * {b}) - {c}"
            
        elif equation_type == "div_sub":
            b = random.randint(2, 12)
            div_val = random.randint(2, 12)
            a = b * div_val
            c = target + div_val
                
            return f"{c} - ({a} / {b})"


class setupscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(30 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(18 * font_size_multiplier))
        title_font = QFont("Helvetica", int(20 * font_size_multiplier), QFont.Bold)
        
        self.title_label = QLabel("experiment configuration")
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        self.subj_label = QLabel("subject number:")
        self.subj_label.setFont(main_font)
        self.subj_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subj_label)
        
        self.subj_combo = QComboBox()
        self.subj_combo.setFont(main_font)
        self.subj_combo.setFixedWidth(int(300 * font_size_multiplier))
        for i in range(1, 100):
            self.subj_combo.addItem(str(i))
        layout.addWidget(self.subj_combo, alignment=Qt.AlignCenter)
        
        self.cond_label = QLabel("condition:")
        self.cond_label.setFont(main_font)
        self.cond_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cond_label)
        
        self.cond_combo = QComboBox()
        self.cond_combo.setFont(main_font)
        self.cond_combo.setFixedWidth(int(300 * font_size_multiplier))
        self.cond_combo.addItems(["training", "baseline", "easy", "hard"])
        layout.addWidget(self.cond_combo, alignment=Qt.AlignCenter)
        
        self.continue_button = QPushButton("continue")
        self.continue_button.setFont(main_font)
        self.continue_button.setFixedWidth(int(300 * font_size_multiplier))
        self.continue_button.setFixedHeight(int(70 * font_size_multiplier))
        self.continue_button.clicked.connect(self.save_and_continue)
        layout.addWidget(self.continue_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def save_and_continue(self):
        global difficulty, subject_number, current_condition
        
        subject_number = self.subj_combo.currentText()
        current_condition = self.cond_combo.currentText()
        
        if current_condition == "hard":
            difficulty = "hard"
        else:
            difficulty = "easy"
            
        send_marker(f"Setup_Complete_Subj_{subject_number}_Cond_{current_condition}_Diff_{difficulty}")
        self.switch_callback()


class startscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.ticks_left = 30
        
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.timer_tick)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(40 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(20 * font_size_multiplier))
        button_font = QFont("Helvetica", int(18 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(48 * font_size_multiplier), QFont.Bold)
        
        intro_text = ("This is the start of the paradigm,<br> you will be given two equations to answer "
                      "<br><br>The results will tell you where in the <b>x, y plane</b> to put the piece you were given <br><br>Have fun")
        
        self.message_label = QLabel(intro_text)
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setContentsMargins(50, 0, 50, 0)
        layout.addWidget(self.message_label)
        
        self.countdown_label = QLabel("")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.hide()
        layout.addWidget(self.countdown_label)

        self.start_button = QPushButton("begin paradigm")
        self.start_button.setFont(button_font)
        self.start_button.setFixedWidth(int(300 * font_size_multiplier))
        self.start_button.setFixedHeight(int(70 * font_size_multiplier))
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def on_start_clicked(self):
        global robot_process
        send_marker("Robot_Started_Waiting_30s")
        
        # launch the robot script
        robot_process = subprocess.Popen(
            [sys.executable, "robot_sequence.py"],
            stdin=subprocess.PIPE,
            text=True
        )
        
        self.start_button.hide()
        self.message_label.setText("Please take the piece from container I.<br><br>Then wait for the next screen.")
        
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

# --- Rest Screen Class ---
class restscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.ticks_left = 30
        
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.timer_tick)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(40 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(24 * font_size_multiplier), QFont.Bold)
        timer_font = QFont("Helvetica", int(60 * font_size_multiplier), QFont.Bold)
        
        self.message_label = QLabel("Great job! Please take a quick rest.<br><br>The next scenario will begin shortly.")
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        
        self.countdown_label = QLabel("30 s")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.countdown_label)
        
        self.setLayout(layout)
        
    def start_rest(self):
        send_marker("Screen_Rest_Started")
        self.ticks_left = 30
        self.countdown_label.setText(f"{self.ticks_left} s")
        self.timer.start(1000)
        
    def timer_tick(self):
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.timer.stop()
            send_marker("Screen_Rest_Finished")
            self.switch_callback()
        else:
            self.countdown_label.setText(f"{self.ticks_left} s")

class intermediatescreen(QWidget):
    def __init__(self, switch_callback, get_scenario_cb):
        super().__init__()
        self.switch_callback = switch_callback
        self.get_scenario_cb = get_scenario_cb
        self.ticks_left = 0
        self.container_one_next = True
        self.position_counter = 1
        
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.timer_tick)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(40 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(20 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(48 * font_size_multiplier), QFont.Bold)
        
        self.message_label = QLabel("")
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setContentsMargins(50, 0, 50, 0)
        
        self.timer_label = QLabel("0 s")
        self.timer_label.setFont(timer_font)
        self.timer_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.message_label)
        layout.addWidget(self.timer_label)
        self.setLayout(layout)
        
    def start_transition(self, x, y, saved_time=0.0):
        if difficulty == "hard":
            base_time = 16
        else:
            base_time = 18
        
        total_time = base_time + math.floor(saved_time)
        container_name = "II" if self.container_one_next else "I"
        
        # Audio Alert for Containers based on scenario
        if difficulty == "hard":
            current_scenario = self.get_scenario_cb()
            if current_scenario in ["audio", "audio_haptic"]:
                if self.container_one_next:
                    audio_sys.play_participant(container1_audio)
                else:
                    audio_sys.play_participant(container2_audio)
        else:
            # If not in hard mode, default to playing alerts
            if self.container_one_next:
                audio_sys.play_participant(container1_audio)
            else:
                audio_sys.play_participant(container2_audio)
        
        self.message_label.setText(
            f"Place the workpiece in coordinate <br><b>({x}, {y})</b><br><br>"
            f"Place a new piece in the package and put it back in Position {self.position_counter}<br>"
            f"After placing it, go to <b>container {container_name}</b> to retrieve the next one and come back"
        )
        
        self.position_counter += 1
        if self.position_counter > 4:
            self.position_counter = 1
            
        self.container_one_next = not self.container_one_next
        self.ticks_left = total_time
        self.timer_label.setText(f"{self.ticks_left} s")
        self.timer.start(1000)
        
    def timer_tick(self):
        self.ticks_left -= 1
        
        if self.ticks_left <= 0:
            self.timer.stop()
            self.switch_callback()
        else:
            self.timer_label.setText(f"{self.ticks_left} s")


class coordinatechallengeapp(QWidget):
    def __init__(self, finish_callback, get_scenario_cb):
        super().__init__()
        self.finish_callback = finish_callback
        self.get_scenario_cb = get_scenario_cb
        
        self.target_x = 0
        self.target_y = 0
        self.time_limit = 15.0
        self.is_red = False
        
        self.attempts = 0
        self.current_eq_x = ""
        self.current_eq_y = ""
        self.start_time = 0.0
        
        self.is_fake_error_trial = False
        self.trials_since_last_fake = 0
        self.next_fake_interval = random.randint(2, 5)
        
        self.ui_timer = QTimer(self)
        self.ui_timer.setTimerType(Qt.PreciseTimer)
        self.ui_timer.timeout.connect(self.update_ui_tick)
        
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setTimerType(Qt.PreciseTimer)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.force_time_over)
        
        self.init_ui()
        
    def init_ui(self):
        master_layout = QGridLayout()
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setSpacing(int(20 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(18 * font_size_multiplier))
        title_font = QFont("Helvetica", int(20 * font_size_multiplier), QFont.Bold)
        time_value_font = QFont("Helvetica", int(90 * font_size_multiplier), QFont.Bold)
        
        self.instructions_label = QLabel("calculate coordinates (1 to 16) to place the piece.")
        self.instructions_label.setFont(title_font)
        self.instructions_label.setAlignment(Qt.AlignCenter)
        self.instructions_label.setMinimumWidth(int(800 * font_size_multiplier))
        self.instructions_label.setWordWrap(True) 
        center_layout.addWidget(self.instructions_label)
        
        self.x_equation_label = QLabel("")
        self.x_equation_label.setFont(main_font)
        self.x_equation_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.x_equation_label)
        
        self.x_entry = QLineEdit()
        self.x_entry.setFont(main_font)
        self.x_entry.setAlignment(Qt.AlignCenter)
        self.x_entry.setPlaceholderText("x coordinate")
        self.x_entry.setFixedWidth(int(250 * font_size_multiplier))
        self.x_entry.setFixedHeight(int(50 * font_size_multiplier))
        center_layout.addWidget(self.x_entry, alignment=Qt.AlignCenter)
        
        self.y_equation_label = QLabel("")
        self.y_equation_label.setFont(main_font)
        self.y_equation_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.y_equation_label)
        
        self.y_entry = QLineEdit()
        self.y_entry.setFont(main_font)
        self.y_entry.setAlignment(Qt.AlignCenter)
        self.y_entry.setPlaceholderText("y coordinate")
        self.y_entry.setFixedWidth(int(250 * font_size_multiplier))
        self.y_entry.setFixedHeight(int(50 * font_size_multiplier))
        center_layout.addWidget(self.y_entry, alignment=Qt.AlignCenter)
        
        self.status_label = QLabel("")
        self.status_label.setFont(main_font)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: red;")
        center_layout.addWidget(self.status_label)
        
        self.submit_button = QPushButton("submit placement")
        self.submit_button.setFont(main_font)
        self.submit_button.setFixedWidth(int(250 * font_size_multiplier))
        self.submit_button.setFixedHeight(int(60 * font_size_multiplier))
        self.submit_button.clicked.connect(self.check_answer)
        center_layout.addWidget(self.submit_button, alignment=Qt.AlignCenter)
        
        self.timer_text_label = QLabel("time remaining:")
        self.timer_text_label.setFont(title_font)
        self.timer_text_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.timer_text_label)
        
        self.timer_value_label = QLabel("15 s")
        self.timer_value_label.setFont(time_value_font)
        self.timer_value_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.timer_value_label)
        
        master_layout.addWidget(center_widget, 0, 1, alignment=Qt.AlignCenter)
        
        self.exit_button = QPushButton("exit paradigm")
        self.exit_button.setFont(main_font)
        self.exit_button.setFixedWidth(int(250 * font_size_multiplier))
        self.exit_button.setFixedHeight(int(60 * font_size_multiplier))
        self.exit_button.clicked.connect(QApplication.instance().quit)
        
        master_layout.addWidget(self.exit_button, 0, 2, alignment=Qt.AlignCenter)
        
        master_layout.setColumnStretch(0, 1)
        master_layout.setColumnStretch(1, 0)
        master_layout.setColumnStretch(2, 1)
        master_layout.setContentsMargins(0, 0, 0, 0)
        
        self.setLayout(master_layout)
        
    def save_to_csv(self, time_taken, is_correct):
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
                writer.writerow(["subject", "condition", "difficulty", "time_taken_s", "correct", "attempts", "equation_x", "equation_y", "is_fake_error"])
            writer.writerow([subject_number, current_condition, difficulty, round(time_taken, 3), is_correct, self.attempts, self.current_eq_x, self.current_eq_y, self.is_fake_error_trial])

    def play_feedback_audio(self, is_correct):
        audio_file = correct_audio if is_correct else incorrect_audio
        if difficulty == "hard":
            current_scenario = self.get_scenario_cb()
            if current_scenario in ["audio", "audio_haptic"]:
                audio_sys.play_participant(audio_file)
        else:
            audio_sys.play_participant(audio_file)
            
    def start_challenge(self):
        self.target_x = random.randint(1, 16)
        self.target_y = random.randint(1, 16)
        
        eq_x = get_equation_for_target(self.target_x, is_x=True)
        eq_y = get_equation_for_target(self.target_y, is_x=False)
        
        self.x_equation_label.setText(f"x equation:  {eq_x}")
        self.y_equation_label.setText(f"y equation:  {eq_y}")
        
        self.x_entry.clear()
        self.y_entry.clear()
        self.status_label.setText("")
        
        self.current_eq_x = eq_x
        self.current_eq_y = eq_y
        self.attempts = 0
        
        self.is_red = False
        self.timer_value_label.setStyleSheet("color: black;")
        self.timer_text_label.setStyleSheet("color: black;")
        self.timer_value_label.setText(f"{int(self.time_limit)} s")
        
        self.start_time = time.perf_counter()
        
        if difficulty == "hard":
            self.trials_since_last_fake += 1
            if self.trials_since_last_fake >= self.next_fake_interval:
                self.is_fake_error_trial = True
                self.trials_since_last_fake = 0
                self.next_fake_interval = random.randint(2, 5)
            else:
                self.is_fake_error_trial = False
        else:
            self.is_fake_error_trial = False
            self.trials_since_last_fake = 0
            
        if self.is_fake_error_trial:
            send_marker(f"MathTask_Start_Target_X{self.target_x}_Y{self.target_y}_FakeError")
        else:
            send_marker(f"MathTask_Start_Target_X{self.target_x}_Y{self.target_y}")
        
        self.ui_timer.start(250)
        self.timeout_timer.start(int(self.time_limit * 1000))
        
    def update_ui_tick(self):
        elapsed = time.perf_counter() - self.start_time
        remaining = self.time_limit - elapsed
        
        if remaining <= 0:
            return
            
        time_seconds = math.ceil(remaining)
        
        if time_seconds <= 5:
            if self.is_red:
                self.timer_value_label.setStyleSheet("color: black;")
                self.timer_text_label.setStyleSheet("color: black;")
                self.is_red = False
            else:
                self.timer_value_label.setStyleSheet("color: red;")
                self.timer_text_label.setStyleSheet("color: red;")
                self.is_red = True
        else:
            self.timer_value_label.setStyleSheet("color: black;")
            self.timer_text_label.setStyleSheet("color: black;")
            
        self.timer_value_label.setText(f"{time_seconds} s")
        
    def force_time_over(self):
        send_marker("MathTask_Timeout")
        self.ui_timer.stop()
        
        elapsed = time.perf_counter() - self.start_time
        self.timer_value_label.setText("0 s")
        self.save_to_csv(elapsed, False)
        
        self.play_feedback_audio(is_correct=False)
        self.finish_callback(self.target_x, self.target_y, 0.0)
        
    def check_answer(self):
        elapsed = time.perf_counter() - self.start_time

        if elapsed >= self.time_limit:
            return
            
        user_x_str = self.x_entry.text()
        user_y_str = self.y_entry.text()
        
        try:
            user_x = int(user_x_str)
            user_y = int(user_y_str)
            
            if not (1 <= user_x <= 16) or not (1 <= user_y <= 16):
                send_marker("MathTask_InvalidBounds")
                self.status_label.setText("coordinates must be between 1 and 16.")
                return
                
            self.attempts += 1
            
            if user_x == self.target_x and user_y == self.target_y:
                if self.is_fake_error_trial:
                    send_marker(f"MathTask_FakeIncorrect_Attempt_{self.attempts}")
                    self.status_label.setText("incorrect, please try again.")
                    self.play_feedback_audio(is_correct=False)
                    return
                
                send_marker(f"MathTask_Correct_Attempt_{self.attempts}")
                self.ui_timer.stop()
                self.timeout_timer.stop()
                
                saved_time = max(0.0, self.time_limit - elapsed)
                self.save_to_csv(elapsed, True)
                self.play_feedback_audio(is_correct=True)
                
                self.finish_callback(self.target_x, self.target_y, saved_time)
            else:
                send_marker(f"MathTask_Incorrect_Attempt_{self.attempts}")
                self.status_label.setText("incorrect, please try again.")
                if difficulty == "hard":
                    self.play_feedback_audio(is_correct=False)
                
        except ValueError:
            send_marker("MathTask_InvalidInput")
            self.status_label.setText("invalid input, please enter integers.")


class paradigmcontroller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("coordinate placement paradigm")
        
        self.current_trial = 0
        self.max_trials = 10 
        
        # Scenario Tracking
        self.scenarios = ["audio", "haptic", "audio_haptic"]
        random.shuffle(self.scenarios)
        self.current_scenario_idx = 0
        self.active_seconds = 0
        self.mistake_on_cooldown = False
        self.pending_rest = False
        
        # Print the randomized order to the terminal immediately upon initialization
        print("\n" + "="*50)
        print("SCENARIO ORDER FOR THIS SESSION:")
        for i, s in enumerate(self.scenarios):
            print(f"  {i+1}. {s.upper()}")
        print("="*50 + "\n")
        
        # Master Timer for Hard Mode (tracks total active time)
        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.master_timer_tick)
        
        self.stacked_widget = QStackedWidget()
        
        self.setup_screen = setupscreen(self.show_start_screen)
        self.start_screen = startscreen(self.start_experiment_tracking) 
        self.intermediate_screen = intermediatescreen(self.show_main_task, self.get_current_scenario)
        self.main_task_screen = coordinatechallengeapp(self.show_intermediate_screen, self.get_current_scenario)
        self.rest_screen = restscreen(self.after_rest_callback)
        
        self.stacked_widget.addWidget(self.setup_screen)        # Index 0
        self.stacked_widget.addWidget(self.start_screen)        # Index 1
        self.stacked_widget.addWidget(self.intermediate_screen) # Index 2
        self.stacked_widget.addWidget(self.main_task_screen)    # Index 3
        self.stacked_widget.addWidget(self.rest_screen)         # Index 4
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)
        
        self.quit_shortcut = QShortcut(QKeySequence("q"), self)
        self.quit_shortcut.activated.connect(QApplication.instance().quit)
        
        # --- F12 Shortcut for Mistake Alert ---
        self.mistake_shortcut = QShortcut(QKeySequence("F12"), self)
        self.mistake_shortcut.activated.connect(self.trigger_mistake)
        
        send_marker("Screen_Setup")
        
    def get_current_scenario(self):
        return self.scenarios[self.current_scenario_idx]
        
    def start_experiment_tracking(self):
        send_marker("Screen_Start_Instructions")
        if difficulty == "hard":
            self.master_timer.start(1000) # Check time every second
            self.announce_scenario()
        self.show_main_task()

    def master_timer_tick(self):
        # Only increment active seconds when the master timer is running (not during rests)
        self.active_seconds += 1
        
        # Target milestones: 300s (5m), 600s (10m), 900s (15m)
        target_time = (self.current_scenario_idx + 1) * 300
        
        if self.active_seconds >= 900: 
            # Reached full 15 minutes of active time
            send_marker("Experiment_Complete_Time_Limit")
            QApplication.instance().quit()
        elif self.active_seconds >= target_time:
            # We reached a 5-minute milestone, cue the rest phase
            self.pending_rest = True

    def announce_scenario(self):
        mode = self.scenarios[self.current_scenario_idx]
        send_marker(f"Scenario_Changed_{mode}")
        
        if mode == "audio":
            audio_sys.play_researcher(mode_audio_only)
        elif mode == "haptic":
            audio_sys.play_researcher(mode_haptic_only)
        elif mode == "audio_haptic":
            audio_sys.play_researcher(mode_audio_haptic)

    def trigger_mistake(self):
        # Enforce the cooldown and ensure we are in hard mode
        if self.mistake_on_cooldown or difficulty != "hard":
            return
            
        send_marker("Manual_Mistake_Alert_Triggered")
        mode = self.scenarios[self.current_scenario_idx]
        
        # Trigger assistance based on the active scenario
        if mode in ["haptic", "audio_haptic"]:
            activate_haptic_vest()
        if mode in ["audio", "audio_haptic"]:
            audio_sys.play_participant(mistake_audio)
            
        # Activate 2-second cooldown
        self.mistake_on_cooldown = True
        QTimer.singleShot(2000, self.reset_mistake_cooldown)

    def reset_mistake_cooldown(self):
        self.mistake_on_cooldown = False

    def show_start_screen(self):
        self.stacked_widget.setCurrentIndex(1)
        
    def show_intermediate_screen(self, x, y, saved_time=0.0):
        global robot_process
        send_marker(f"Screen_Intermediate_Picking_Piece_Target_X{x}_Y{y}")
        
        if robot_process is not None and robot_process.poll() is None:
            try:
                robot_process.stdin.write("continue\n")
                robot_process.stdin.flush()
            except Exception:
                pass
                
        self.intermediate_screen.start_transition(x, y, saved_time)
        self.stacked_widget.setCurrentIndex(2)
        
    def show_main_task(self):
        # Check if we need to take a break before the next trial begins
        if difficulty == "hard" and self.pending_rest:
            self.pending_rest = False
            self.master_timer.stop() # pause the active experiment timer
            self.rest_screen.start_rest()
            self.stacked_widget.setCurrentIndex(4) # show rest screen
            return

        # In non-hard mode, respect the 10 trial limit
        if difficulty != "hard" and self.current_trial >= self.max_trials:
            send_marker("Experiment_Complete_Trial_Limit")
            QApplication.instance().quit()
            return
            
        self.current_trial += 1
        send_marker(f"Screen_MathTask_Trial_{self.current_trial}")
        
        self.main_task_screen.start_challenge()
        self.stacked_widget.setCurrentIndex(3)

    def after_rest_callback(self):
        # Proceed to the next scenario
        self.current_scenario_idx += 1
        self.announce_scenario()
        
        # Resume the master timer
        self.master_timer.start(1000)
        
        # Launch the next trial
        self.current_trial += 1
        send_marker(f"Screen_MathTask_Trial_{self.current_trial}")
        
        self.main_task_screen.start_challenge()
        self.stacked_widget.setCurrentIndex(3)


def cleanup_resources():
    global robot_process
    send_marker("Application_Closing")
    
    if robot_process is not None:
        robot_process.terminate()
        
    if haptic_loop is not None:
        future = asyncio.run_coroutine_threadsafe(close_haptics(), haptic_loop)
        try:
            future.result(timeout=2)
        except Exception as e:
            print(f"Error closing haptics: {e}")
        haptic_loop.call_soon_threadsafe(haptic_loop.stop)


def run_paradigm():
    init_lsl()
    start_haptic_thread()
    
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_resources)
    
    # Configure specific hardware routing 
    audio_sys.setup_devices(participant_keyword="Beats", researcher_keyword="Realtek")
    
    controller = paradigmcontroller()
    
    screens = app.screens()
    if len(screens) > 1:
        second_screen = screens[1].geometry()
        controller.move(second_screen.left(), second_screen.top())
        
    controller.showFullScreen()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_paradigm()