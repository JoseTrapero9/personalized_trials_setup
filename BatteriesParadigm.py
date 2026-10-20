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
import re
import bhaptics_python
import sounddevice as sd
import soundfile as sf

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, 
                             QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QStackedWidget,
                             QShortcut, QComboBox, QGridLayout, QCheckBox, QGroupBox, QFrame,
                             QListWidget, QAbstractItemView, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence, QPixmap, QFontMetrics
from pylsl import StreamInfo, StreamOutlet

base_dir = os.path.dirname(os.path.abspath(__file__))
audio_dir = os.path.join(base_dir, "audios")

correct_audio = os.path.join(audio_dir, "correct_answer.wav") 
incorrect_audio = os.path.join(audio_dir, "loud_incorrect_answer.wav")
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

# ---------------------------------------------------------------------------
# Timing / training configuration
# ---------------------------------------------------------------------------
RETRIEVAL_SECONDS = 20          # container retrieval phase
TASK_SECONDS_DEFAULT = 20       # assembly time in baseline / easy / hard (non-robot) scenarios
WARNING_SECONDS = 10            # red timer + blinking warning starts at this many seconds left

TRAINING_SECONDS = 180          # length of the practice round (3 min, baseline-like)
LOG_TRAINING_CSV = False        # training is NOT a measurement -> no performance CSV by default
TRAINING_MARKER_PREFIX = "TRAIN_"
training_active = False         # set to True when condition == "training"

def init_lsl():
    global marker_outlet
    info = StreamInfo('ParadigmMarkers', 'Markers', 1, 0, 'string', 'pyqt_paradigm_123')
    marker_outlet = StreamOutlet(info)
    print("LSL Marker Outlet initialized.")

def send_marker(marker_string):
    global marker_outlet
    # Everything sent during the training session is tagged so it can never be
    # mistaken for measurement data in the LSL recording.
    if training_active:
        marker_string = TRAINING_MARKER_PREFIX + marker_string
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

    def start_looping_alarm(self, filepath, volume=0.3):
        if self.alarm_active or not os.path.exists(filepath):
            return
        self.alarm_active = True
        # pass volume parameter to the background worker thread
        threading.Thread(
            target=self._loop_worker,
            args=(filepath, self.researcher_device, volume),
            daemon=True,
        ).start()

    def stop_looping_alarm(self):
        self.alarm_active = False
        sd.stop()

    def _loop_worker(self, filepath, device_id, volume=0.3):
        try:
            data, fs = sf.read(filepath, dtype='float32')
            # scale the waveform amplitude to reduce acoustic intensity
            scaled_data = data * volume
            while self.alarm_active:
                sd.play(scaled_data, samplerate=fs, device=device_id)
                sd.wait()
        except Exception as e:
            print(f'Alarm loop error: {e}')

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

difficulty = "hard"
subject_number = "1"
current_condition = "training"
active_scenarios_list = []
robot_process = None

def load_synch_sequence(path=os.path.join(base_dir, "log_files", "s01_fast.txt")):
    sequence = []
    if not os.path.exists(path):
        print(f"Warning: File not found at {path}. Using fallback sequence.")
        for i in range(1, 41):
            sequence.append(("text", random.choice([6, 7, 8, 9]), "Assemble accordingly"))
        return sequence

    with open(path, "r", encoding="utf-8-sig") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    for line in raw_lines:
        lower_line = line.lower()
        if lower_line.startswith(("piece", "mode", "trial")):
            continue

        if "\t" in line:
            tokens = [t.strip() for t in line.split("\t") if t.strip()]
        elif "," in line and not re.search(r'\s{2,}', line):
            tokens = [t.strip() for t in next(csv.reader([line])) if t.strip()]
        else:
            tokens = [t.strip() for t in re.split(r'\s{2,}', line) if t.strip()]

        if not tokens:
            continue

        if tokens[0].lower() == "image" and len(tokens) >= 2:
            sequence.append(("image", tokens[1], None))
            continue
        elif len(tokens) >= 3 and tokens[1].lower() == "image":
            sequence.append(("image", tokens[2], None))
            continue

        if tokens[0].lower() == "text" and len(tokens) >= 3:
            try:
                sequence.append(("text", int(tokens[1]), tokens[2]))
                continue
            except ValueError:
                pass

        if len(tokens) >= 3:
            try:
                target_sum = int(tokens[1])
                instruction_text = tokens[2]
                sequence.append(("text", target_sum, instruction_text))
                continue
            except ValueError:
                pass

        match = re.match(r'^\s*(\d+)\s+(\d+)\s+(.+?)(?:\s{2,}|\t)(.+)$', line)
        if match:
            try:
                target_sum = int(match.group(2))
                instruction_text = match.group(3).strip()
                sequence.append(("text", target_sum, instruction_text))
                continue
            except ValueError:
                pass

    print(f"\n--- Loaded {len(sequence)} Tasks From Sequence ---")
    for i, (m, p1, p2) in enumerate(sequence[:3]):
        print(f"Task {i+1}: Sum={p1}, Instruction='{p2}'")
    print("------------------------------------------\n")
    return sequence

WORKPIECE_SEQUENCE = load_synch_sequence()

TRAINING_SEQUENCE = []
COLOR_NAMES = {1: "Blue", 2: "Red", 3: "Yellow", 4: "Green"}

def format_battery_instruction(colors):
    """(2, 2, 1) -> 'Use 2 red and 1 blue'  (same style as the hard-condition instructions)."""
    counts = {}
    for c in colors:
        counts[c] = counts.get(c, 0) + 1
    parts = [f"{n} {COLOR_NAMES[c].lower()}" for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    if len(parts) == 1:
        return f"Use {parts[0]}"
    return "Use " + ", ".join(parts[:-1]) + " and " + parts[-1]

def slot_sum(order):
    """order = colour values for slot 1, 2, 3."""
    return sum(v * (i + 1) for i, v in enumerate(order))

def build_training_sequence(n_tasks=12, seed=None):
    """Tasks used ONLY in the training round, so the participant never rehearses
    the exact tasks of the measured baseline.

    1) If log_files/training.txt exists it is parsed with the same parser as the
       measurement sequence (same file format).
    2) Otherwise tasks are generated like the real ones: the instruction names the
       three batteries ("Use 2 red and 1 blue"), the target sum decides the order
       (sum = colour1*1 + colour2*2 + colour3*3). Only combinations whose target
       sum is reached by exactly one order are used, so every task has a single
       correct answer.
    """
    path = os.path.join(base_dir, "log_files", "training.txt")
    if os.path.exists(path):
        seq = load_synch_sequence(path)
        if seq:
            return seq

    import itertools
    rng = random.Random(seed)
    pool = []
    for combo in itertools.combinations_with_replacement(range(1, 5), 3):
        orders = set(itertools.permutations(combo))
        sums = [slot_sum(o) for o in orders]
        for o in orders:
            if sums.count(slot_sum(o)) == 1 and len(orders) > 1:   # skip all-same-colour (no decision)
                pool.append((combo, slot_sum(o)))

    seq, last = [], None
    while len(seq) < n_tasks:
        combo, total = rng.choice(pool)
        if combo == last:
            continue
        last = combo
        seq.append(("text", total, format_battery_instruction(combo)))
    return seq

def auto_fit_label(label, text, max_size=46, min_size=18, margin=40):
    """Dynamically scales font size to guarantee text fits on a single line."""
    label.setText(text)
    available_width = label.width()
    if available_width <= 100:
        available_width = 1000
    
    target_width = max(available_width - margin, 100)
    font = label.font()
    for size in range(max_size, min_size - 1, -1):
        font.setPointSize(size)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        if text_width <= target_width:
            break
    label.setFont(font)

def make_training_tag():
    """Small pill shown on the task screens while the training round runs."""
    tag = QLabel("TRAINING")
    tag.setAlignment(Qt.AlignCenter)
    tag.setFont(QFont("Helvetica", 18, QFont.Bold))
    tag.setStyleSheet("color: #B85C00; background-color: #FFF1DE; "
                      "border-radius: 12px; padding: 4px 18px; letter-spacing: 3px;")
    tag.hide()
    return tag

class setupscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)
        
        main_font = QFont("Helvetica", 24)
        title_font = QFont("Helvetica", 24, QFont.Bold)
        
        self.title_label = QLabel("Experiment Configuration")
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)
        
        self.subj_label = QLabel("Subject Number:")
        self.subj_label.setFont(main_font)
        layout.addWidget(self.subj_label, alignment=Qt.AlignCenter)
        
        self.subj_combo = QComboBox()
        self.subj_combo.setFont(main_font)
        self.subj_combo.setFixedWidth(280)
        for i in range(1, 100):
            self.subj_combo.addItem(str(i))
        layout.addWidget(self.subj_combo, alignment=Qt.AlignCenter)
        
        self.cond_label = QLabel("Condition:")
        self.cond_label.setFont(main_font)
        layout.addWidget(self.cond_label, alignment=Qt.AlignCenter)
        
        self.cond_combo = QComboBox()
        self.cond_combo.setFont(main_font)
        self.cond_combo.setFixedWidth(280)
        self.cond_combo.addItems(["training", "baseline", "easy", "hard", "manual"])
        self.cond_combo.currentTextChanged.connect(self.on_condition_changed)
        layout.addWidget(self.cond_combo, alignment=Qt.AlignCenter)
        
        self.scenario_group = QGroupBox("Order Scenarios (Drag & Drop, Check to Include)")
        self.scenario_group.setFont(main_font)
        group_layout = QVBoxLayout()

        self.scenario_list_widget = QListWidget()
        self.scenario_list_widget.setFont(main_font)
        self.scenario_list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.scenario_list_widget.setDefaultDropAction(Qt.MoveAction)
        self.scenario_list_widget.setFixedWidth(360)
        self.scenario_list_widget.setFixedHeight(150)

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
        self.continue_button.setFixedWidth(280)
        self.continue_button.setFixedHeight(50)
        self.continue_button.clicked.connect(self.save_and_continue)
        layout.addWidget(self.continue_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def on_condition_changed(self, text):
        self.scenario_group.setEnabled(text == "manual")
        
    def save_and_continue(self):
        global difficulty, subject_number, current_condition, active_scenarios_list, training_active
        
        subject_number = self.subj_combo.currentText()
        current_condition = self.cond_combo.currentText()
        training_active = (current_condition == "training")
        
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
        layout.setSpacing(25)
        
        main_font = QFont("Helvetica", 28)
        button_font = QFont("Helvetica", 26)
        timer_font = QFont("Helvetica", 72, QFont.Bold)
        
        intro_text = ("<b>Paradigm Start</b><br><br>"
                      "1. Retrieve parts from Container I or II.<br>"
                      "2. Observe the objective and assemble according to color and slot rules.<br>"
                      "3. You have <b>25 seconds</b> before the alarm triggers.<br><br>"
                      "Press <b>Left</b> for Point 1<br>"
                      "Press <b>Right</b> for Point 2")
        
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
        self.start_button.setFixedWidth(280)
        self.start_button.setFixedHeight(60)
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def set_training_mode(self):
        self.message_label.setText(
            "<b>Training Session</b><br><br>"
            "1. Retrieve parts from Container I or II.<br>"
            "2. Observe the objective and assemble according to color and slot rules.<br>"
            f"3. You have <b>{TASK_SECONDS_DEFAULT} seconds</b> per assembly before the alarm triggers.<br><br>"
            "Press <b>Left</b> for Point 1<br>"
            "Press <b>Right</b> for Point 2<br><br>"
            f"This practice round lasts <b>{TRAINING_SECONDS // 60} minutes</b> "
            "and is not recorded as a measurement."
        )
        self.start_button.setText("Start Training")

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
        layout.setSpacing(25)
        main_font = QFont("Helvetica", 38, QFont.Bold)
        timer_font = QFont("Helvetica", 80, QFont.Bold)
        
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
        layout.setSpacing(25)
        
        main_font = QFont("Helvetica", 30, QFont.Bold)
        button_font = QFont("Helvetica", 30)
        
        self.message_label = QLabel("You have completed a block of 3 scenarios.<br><br>Please take a longer break.<br>Press the button when you are ready to continue.")
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        self.resume_button = QPushButton("Continue Measurements")
        self.resume_button.setFont(button_font)
        self.resume_button.setFixedWidth(340)
        self.resume_button.setFixedHeight(70)
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
        self.ticks_left = 18
        self.container_toggle = True
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(25)

        main_font = QFont("Helvetica", 48)
        timer_font = QFont("Helvetica", 80, QFont.Bold)

        self.training_tag = make_training_tag()
        layout.addWidget(self.training_tag, alignment=Qt.AlignCenter)

        self.instruction_label = QLabel("")
        self.instruction_label.setFont(main_font)
        self.instruction_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.instruction_label)

        self.timer_label = QLabel("18 s")
        self.timer_label.setFont(timer_font)
        self.timer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.timer_label)

        self.setLayout(layout)

    def start_retrieval(self):
<<<<<<< HEAD
        self.ticks_left = RETRIEVAL_SECONDS
=======
        self.ticks_left = 18
>>>>>>> 7028787b3ccedcfca5c13835a7589e2e456dca73
        target_container = "I" if self.container_toggle else "II"
        self.instruction_label.setText(f"BRING BACK EMPTY PIECE!<br>Retrieve the parts from <b>Container {target_container}</b>")
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
        
        self.current_trial_num = 0
        self.evaluated = False
        self.assembly_status = "none"
        self.pending_log = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self.toggle_warning_blink)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Left Panel (Task Workspace)
        self.left_panel = QFrame()
        self.left_panel.setFrameShape(QFrame.StyledPanel)
        self.left_panel.setStyleSheet("background-color: white; border-radius: 10px;")
        
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(30, 20, 30, 20)
        
        # Top flexible spacer
        left_layout.addStretch(1)

        self.training_tag = make_training_tag()
        left_layout.addWidget(self.training_tag, alignment=Qt.AlignCenter)

        # Header title
        self.header_label = QLabel("INPUT CORRECT CONFIGURATION")
        self.header_label.setFont(QFont("Helvetica", 30, QFont.Bold))
        self.header_label.setStyleSheet("color: #777; letter-spacing: 2px;")
        self.header_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.header_label)

        left_layout.addSpacing(4)

        # Centered Huge Countdown Timer (Immediate visibility)
        self.timer_label = QLabel("25 s")
        self.timer_label.setFont(QFont("Helvetica", 100, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #111;")
        left_layout.addWidget(self.timer_label)

        # Centered Warning indicator
        self.warning_label = QLabel("")
        self.warning_label.setFont(QFont("Helvetica", 60, QFont.Bold))  # Increased font size
        self.warning_label.setStyleSheet("color: red; letter-spacing: 1px;")
        self.warning_label.setAlignment(Qt.AlignCenter)
        
        # Set height to 75–80px to accommodate a 50–55pt font without clipping
        self.warning_label.setFixedHeight(80) 
        left_layout.addWidget(self.warning_label)

        left_layout.addSpacing(15)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.image_label)

        # Dedicated Target Sum Label
        self.target_sum_label = QLabel()
        self.target_sum_label.setAlignment(Qt.AlignCenter)
        self.target_sum_label.setStyleSheet("font-weight: bold; color: #222;")
        left_layout.addWidget(self.target_sum_label)

        left_layout.addSpacing(10)

        # Dedicated Instruction Label (Dynamic auto-fit up to 46pt, single line)
        self.instruction_label = QLabel()
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.instruction_label.setStyleSheet("font-weight: bold; color: #0056B3;")
        self.instruction_label.setWordWrap(False)
        left_layout.addWidget(self.instruction_label)

        # Bottom flexible spacer
        left_layout.addStretch(1)

        # Handover instructions
        self.handover_label = QLabel()
        self.handover_label.setFont(QFont("Helvetica", 25))
        self.handover_label.setAlignment(Qt.AlignCenter)
        self.handover_label.setStyleSheet("color: #222; padding: 10px; background-color: #F0F4F8; border-radius: 6px;")
        left_layout.addWidget(self.handover_label)

        # Right Panel (Rules Card)
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.StyledPanel)
        self.right_panel.setStyleSheet("background-color: #FAFAFA; border-radius: 10px;")
        self.right_panel.setFixedWidth(260)
        
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setAlignment(Qt.AlignTop)
        right_layout.setSpacing(10)

        rules_head = QLabel("Rules")
        rules_head.setFont(QFont("Helvetica", 44, QFont.Bold))
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
        rules_colors.setFont(QFont("Helvetica", 28))
        right_layout.addWidget(rules_colors)

        main_layout.addWidget(self.left_panel, 1)
        main_layout.addWidget(self.right_panel)
        self.setLayout(main_layout)

    def start_task(self, trial_num, target_pt):
        self.flush_pending_log()

        scenario = self.get_scenario_cb()
        if scenario == "robot_fast":
            self.ticks_left = 15
        elif scenario == "robot_slow":
            self.ticks_left = 25
        else:
            self.ticks_left = TASK_SECONDS_DEFAULT

        self.current_trial_num = trial_num
        self.evaluated = False
        self.assembly_status = "none"
        self.pending_log = None

        self.alarm_triggered = False
        self.active_collection_pt = target_pt
        self.task_start_time = time.perf_counter()
        self.warn_visible = False

        seq = TRAINING_SEQUENCE if (training_active and TRAINING_SEQUENCE) else WORKPIECE_SEQUENCE
        idx = (trial_num - 1) % len(seq)
        mode, p1, p2 = seq[idx]

        if mode == "image":
            self.target_sum_label.hide()
            self.instruction_label.hide()
            self.image_label.show()
            self.current_task_info = f"image_{p1}"
            img_path = os.path.join(base_dir, "workpieces", p1)
            if os.path.exists(img_path):
                pixmap = QPixmap(img_path)
                self.image_label.setPixmap(pixmap.scaledToWidth(320, Qt.SmoothTransformation))
            else:
                self.image_label.setText(f"[Image: {p1}]")
        else:
            self.image_label.clear()
            self.image_label.hide()
            self.target_sum_label.show()
            self.instruction_label.show()
            self.current_task_info = f"sum_{p1}_{p2}"
            
            auto_fit_label(self.target_sum_label, f"Sum must be {p1}", max_size=36, min_size=24)
            auto_fit_label(self.instruction_label, str(p2), max_size=46, min_size=24)

        pt_name = "Point 1" if target_pt == 1 else "Point 2"
        key_hint = "Left" if target_pt == 1 else "Right"

        self.handover_label.setText(
            f"Place the workpiece at <b>{pt_name}</b>. Press <b>{key_hint}</b> upon completion."
        )

        self.timer_label.setStyleSheet("color: black;")
        self.timer_label.setText(f"{self.ticks_left} s")
        self.warning_label.setText("")
        self.blink_timer.stop()
        
        send_marker(f"Workpiece_Task_Started_Trial_{trial_num}_Type_{self.current_task_info}")
        self.timer.start(1000)

    def record_evaluation(self, is_correct):
        if self.current_trial_num == 0 or self.evaluated:
            return

        self.evaluated = True
        self.assembly_status = "correct" if is_correct else "incorrect"
        send_marker(f"Assembly_Evaluated_{self.assembly_status}")

        if not is_correct:
            audio_sys.play_participant(incorrect_audio)

        if self.pending_log is not None:
            self.pending_log["assembly_status"] = self.assembly_status
            self._write_csv_row(self.pending_log)
            self.pending_log = None

    def toggle_warning_blink(self):
        self.warn_visible = not self.warn_visible
        self.warning_label.setText("WARNING - FINISH" if self.warn_visible else "")

    def timer_tick(self):
        self.ticks_left -= 1
        
        # Start blinking when WARNING_SECONDS or fewer remain
        if 0 < self.ticks_left <= WARNING_SECONDS:
            self.timer_label.setStyleSheet("color: red;")
            if not self.blink_timer.isActive():
                self.warn_visible = True
                self.warning_label.setText("WARNING - FINISH")
                self.blink_timer.start(250)
        
        # When time runs out, keep blinking active
        if self.ticks_left <= 0:
            self.timer_label.setText("0 s")
            self.timer_label.setStyleSheet("color: red;")
            
            # Ensure the blink timer stays active if time ran out without triggering 10s warning
            if not self.blink_timer.isActive():
                self.warn_visible = True
                self.warning_label.setText("WARNING - FINISH")
                self.blink_timer.start(250)
            
            if not self.alarm_triggered:
                self.alarm_triggered = True
                send_marker("Workpiece_Task_Overtime_Alarm_Started")
                audio_sys.start_looping_alarm(alarm_audio, volume=0.9)
        else:
            self.timer_label.setText(f"{self.ticks_left} s")

    def handover_received(self, point_pressed):
        if self.active_collection_pt is None or point_pressed != self.active_collection_pt:
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

        if self.evaluated:
            self._write_csv_row(log_data)
            self.pending_log = None
        else:
            self.pending_log = log_data
        
        self.active_collection_pt = None
        self.finish_callback(point_pressed)

    def flush_pending_log(self):
        if self.pending_log is not None:
            self._write_csv_row(self.pending_log)
            self.pending_log = None

    def _write_csv_row(self, log_dict):
        # The training round is practice, not measurement: no performance log.
        if training_active and not LOG_TRAINING_CSV:
            return

        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        try:
            subj_int = int(subject_number)
            subj_str = f"s{subj_int:02d}"
        except ValueError:
            subj_str = f"s_{subject_number}"

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{subj_str}_{current_condition}_{timestamp}.csv"
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

class tutorialscreen(QWidget):
    """Step-by-step training tutorial. One screen at a time, no time pressure.

    Navigation (participant): Right button (F14) = next, Left button (F13) = back.
    Navigation (experimenter): mouse buttons or the arrow keys.
    The 'Try the buttons' step requires a press on both hardware buttons, which
    doubles as a quick check that F13 / F14 reach the application.
    """

    COLORS = [("Blue", 1, "#2F6FDE", "white"),
              ("Red", 2, "#D93A3A", "white"),
              ("Yellow", 3, "#F2C200", "#222"),
              ("Green", 4, "#2E9E4F", "white")]

    forced_scale = None     # e.g. 1.0 to disable auto-scaling

    def __init__(self, finish_callback):
        super().__init__()
        self.finish_callback = finish_callback
        self.k = self._compute_scale()
        self.current_step = 0
        self.buttons_seen = set()
        self.check_step = None
        self.check_cards = {}
        self.pages_meta = []

        self.setObjectName("tutorial")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QWidget#tutorial { background-color: #F5F7FA; }")
        self.setFocusPolicy(Qt.StrongFocus)
        self.init_ui()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _compute_scale():
        """Designed for a 1080p participant screen; shrink proportionally on smaller ones."""
        if tutorialscreen.forced_scale:
            return tutorialscreen.forced_scale
        screens = QApplication.screens()
        if not screens:
            return 1.0
        target = screens[1] if len(screens) > 1 else screens[0]
        return max(0.6, min(1.0, target.size().height() / 1080.0))

    def _pt(self, size):
        return max(9, int(round(size * self.k)))

    def _px(self, value):
        return max(1, int(round(value * self.k)))

    def _text(self, html, size=26, bold=False, color="#222", align=Qt.AlignCenter, wrap=True):
        lab = QLabel(html)
        lab.setTextFormat(Qt.RichText)
        lab.setFont(QFont("Helvetica", self._pt(size), QFont.Bold if bold else QFont.Normal))
        lab.setStyleSheet(f"color: {color};")
        lab.setAlignment(align)
        lab.setWordWrap(wrap)
        return lab

    def _line(self, html, size=26, bold=False, color="#222", align=Qt.AlignCenter):
        """Single-line label (no word wrap) - used inside the illustrations so
        layouts size themselves exactly and nothing gets clipped."""
        return self._text(html, size, bold, color, align, wrap=False)

    def _card(self, border="#D5DBE3", bg="white"):
        frame = QFrame()
        frame.setObjectName("card")
        frame.setStyleSheet(f"QFrame#card {{ background-color: {bg}; border: 3px solid {border}; "
                            f"border-radius: 14px; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignCenter)
        return frame, lay

    def _chip(self, text, bg, fg="white", size=24):
        chip = QLabel(text)
        chip.setAlignment(Qt.AlignCenter)
        chip.setFont(QFont("Helvetica", self._pt(size), QFont.Bold))
        chip.setStyleSheet(f"background-color: {bg}; color: {fg}; border-radius: 12px; "
                           f"padding: {self._px(8)}px {self._px(22)}px;")
        return chip

    @staticmethod
    def _row(widgets, spacing=20):
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)
        lay.setAlignment(Qt.AlignCenter)
        for w in widgets:
            lay.addWidget(w)
        return holder

    @staticmethod
    def _column(widgets, spacing=14):
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)
        lay.setAlignment(Qt.AlignCenter)
        for w in widgets:
            lay.addWidget(w, alignment=Qt.AlignCenter)
        return holder

    def _arrow(self):
        arrow = self._line("&rarr;", 44, True, "#8A94A3")
        arrow.setFixedWidth(self._px(60))
        return arrow

    # ---------------------------------------------------------------------- UI
    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 28, 60, 24)
        root.setSpacing(14)

        top = QHBoxLayout()
        tag = QLabel("TRAINING  \u00b7  TUTORIAL")
        tag.setFont(QFont("Helvetica", self._pt(18), QFont.Bold))
        tag.setStyleSheet("color: #B85C00; background-color: #FFF1DE; border-radius: 12px; "
                          "padding: 4px 18px; letter-spacing: 3px;")
        self.step_counter = QLabel("")
        self.step_counter.setFont(QFont("Helvetica", self._pt(20)))
        self.step_counter.setStyleSheet("color: #667085;")
        top.addWidget(tag)
        top.addStretch(1)
        top.addWidget(self.step_counter)
        root.addLayout(top)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self._build_pages()

        nav = QHBoxLayout()
        self.back_button = QPushButton("\u2190  Back")
        self.next_button = QPushButton("Next  \u2192")
        for b in (self.back_button, self.next_button):
            b.setFont(QFont("Helvetica", self._pt(24)))
            b.setFixedHeight(self._px(64))
            b.setMinimumWidth(self._px(220))
            b.setFocusPolicy(Qt.NoFocus)
        self.back_button.setStyleSheet(
            "QPushButton { background: white; color: #344054; border: 2px solid #C5CCD6; border-radius: 12px; }"
            "QPushButton:disabled { color: #B5BCC7; border-color: #E1E5EA; }")
        self.next_button.setStyleSheet(
            "QPushButton { background: #2F6FDE; color: white; border: none; border-radius: 12px; }"
            "QPushButton:pressed { background: #2459B5; }")
        self.back_button.clicked.connect(self.prev_step)
        self.next_button.clicked.connect(self.next_step)

        self.dots_label = QLabel("")
        self.dots_label.setFont(QFont("Helvetica", self._pt(22)))
        self.dots_label.setStyleSheet("color: #2F6FDE; letter-spacing: 4px;")
        self.dots_label.setAlignment(Qt.AlignCenter)

        nav.addWidget(self.back_button)
        nav.addWidget(self.dots_label, 1)
        nav.addWidget(self.next_button)
        root.addLayout(nav)

        self.exp_hint = QLabel("Experimenter: mouse or \u2190 / \u2192 arrow keys also navigate.")
        self.exp_hint.setFont(QFont("Helvetica", self._pt(13)))
        self.exp_hint.setStyleSheet("color: #98A2B3;")
        self.exp_hint.setAlignment(Qt.AlignCenter)
        root.addWidget(self.exp_hint)

        self._show_step(0, send=False)   # no marker while the app is still building its screens

    def _add_page(self, title, body, illustration=None, hint=None, exp_note=None):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(14)

        lay.addWidget(self._text(title, 40, True, "#101828"))
        lay.addWidget(self._text(body, 25, False, "#344054"))
        lay.addStretch(1)
        if illustration is not None:
            lay.addWidget(illustration, alignment=Qt.AlignCenter)
        lay.addStretch(1)
        if hint:
            hint_lab = self._text(hint, 22, False, "#475467")
            hint_lab.setStyleSheet("color: #475467; background-color: #EAF1FF; border-radius: 10px; padding: 10px 18px;")
            lay.addWidget(hint_lab)
        if exp_note:
            lay.addWidget(self._text(exp_note, 14, False, "#98A2B3"))

        self.pages.addWidget(page)
        self.pages_meta.append(title)
        return len(self.pages_meta) - 1

    def _build_pages(self):
        R, T, W = RETRIEVAL_SECONDS, TASK_SECONDS_DEFAULT, WARNING_SECONDS

        self._add_page(
            "Welcome to the training",
            "Before the real experiment starts, you will learn the task <b>step by step</b> "
            "(about 2 minutes). Afterwards you practice for "
            f"<b>{TRAINING_SECONDS // 60} minutes</b> \u2013 exactly like the real task, "
            "but <b>nothing you do here counts</b>.",
            self._ill_welcome(),
            hint="Right button \u2192 next screen &nbsp;&nbsp;\u00b7&nbsp;&nbsp; Left button \u2192 previous screen")

        self._add_page(
            "Your task: repeat this cycle",
            "Every round has three parts. A new round starts as soon as you have handed over a workpiece.",
            self._ill_cycle())

        self._add_page(
            "1 \u00b7 Retrieve the parts",
            "The screen tells you which container to use. The containers alternate: "
            "<b>I, II, I, II \u2026</b> You also hear the container name in your headphones.",
            self._ill_retrieval(),
            hint=f"You have <b>{R} seconds</b> to get the parts.")

        self._add_page(
            "2 \u00b7 Learn the rules",
            "Every color has a <b>value</b> and every slot has a <b>multiplier</b>. "
            "The sum of an assembly is <b>color value \u00d7 slot multiplier</b>, added up over the three slots.",
            self._ill_rules(),
            hint="These rules stay visible on the right side of the screen while you assemble.")

        self._add_page(
            "2 \u00b7 Example: the task",
            "Each task shows a <b>target sum</b> and an <b>instruction</b>. The instruction tells you "
            "<b>which three batteries</b> to use \u2013 one for each slot.",
            self._ill_example(show_solution=False),
            hint="Your job: find the <b>order</b> of these batteries that gives the target sum.")

        self._add_page(
            "2 \u00b7 Example: the solution",
            "Put one battery in each slot and add up <b>color value \u00d7 slot multiplier</b>.",
            self._ill_example(show_solution=True),
            hint="The same batteries give different sums in a different order "
                 "(Blue, Red, Red would give 11) \u2013 only one order hits the target.")

        self._add_page(
            "Watch the clock",
            f"You have <b>{T} seconds</b> for each assembly.",
            self._ill_clock(),
            hint="No need to panic: just finish and hand over \u2013 the alarm stops as soon as you press the button.")

        self._add_page(
            "3 \u00b7 Hand over",
            "When the workpiece is finished, place it at the handover point shown on the screen "
            "and press the matching button.",
            self._ill_handover(),
            hint="Only the button shown on the screen counts. Your press tells the robot that the workpiece is ready.")

        self.check_step = self._add_page(
            "Try the buttons",
            "Press the <b>Left</b> button and then the <b>Right</b> button.",
            self._ill_check(),
            exp_note="Experimenter: both hardware buttons (F13 / F14) must light up here. "
                     "Use the mouse to skip this check.")

        self._add_page(
            "Feedback and alerts",
            "After each hand over, the experimenter checks your assembly. If it is <b>incorrect</b>, you hear an "
            "error tone. In the real experiment you may also get a <b>warning</b> while you work \u2013 a sound "
            "and/or a vibration of the vest. It means: double-check your assembly.",
            self._ill_alerts(),
            hint="This practice round has no warnings \u2013 only the error tone after a wrong assembly.",
            exp_note="Experimenter: click a button to play the sample.")

        self._add_page(
            "Ready to practice?",
            f"You will now practice for <b>{TRAINING_SECONDS // 60} minutes</b>. It works like the real task, "
            "but nothing you do counts as a measurement. If anything is unclear, "
            "<b>ask the experimenter now</b>.",
            self._ill_ready())

    # ------------------------------------------------------------ illustrations
    def _ill_welcome(self):
        parts = []
        for num, txt, col in [("1", "Tutorial", "#2F6FDE"),
                              (2, f"Practice ({TRAINING_SECONDS // 60} min)", "#2E9E4F"),
                              (3, "Real experiment", "#667085")]:
            card, lay = self._card(border=col)
            lay.addWidget(self._chip(str(num), col, size=28), alignment=Qt.AlignCenter)
            lay.addWidget(self._line(txt, 26, True, col))
            card.setMinimumWidth(self._px(300))
            parts.append(card)
        return self._row([parts[0], self._arrow(), parts[1], self._arrow(), parts[2]])

    def _ill_cycle(self):
        cards = []
        for num, head, sub, col in [
                ("1", "RETRIEVE", "Get the parts from the container", "#2F6FDE"),
                ("2", "ASSEMBLE", "Build the workpiece following the rules", "#2E9E4F"),
                ("3", "HAND OVER", "Place it at the point shown and press the button", "#B85C00")]:
            card, lay = self._card(border=col)
            lay.addWidget(self._chip(num, col, size=28), alignment=Qt.AlignCenter)
            lay.addWidget(self._line(head, 28, True, col))
            lay.addWidget(self._text(sub, 22))
            card.setFixedWidth(self._px(360))
            card.setMinimumHeight(self._px(220))
            cards.append(card)
        loop = self._line("\u21bb  then start again with the next round", 24, False, "#667085")
        return self._column([self._row([cards[0], self._arrow(), cards[1], self._arrow(), cards[2]]), loop])

    def _ill_retrieval(self):
        card, lay = self._card()
        lay.addWidget(self._line("Retrieve the parts from <b>Container I</b>", 34))
        lay.addWidget(self._line(f"{RETRIEVAL_SECONDS} s", 64, True, "#111"))
        card.setFixedWidth(self._px(900))
        return card

    def _ill_rules(self):
        chips = [self._chip(f"{name}  =  {val}", bg, fg, 28) for name, val, bg, fg in self.COLORS]
        slots = []
        for k in (1, 2, 3):
            card, lay = self._card()
            lay.addWidget(self._line(f"Slot {k}", 26, True))
            lay.addWidget(self._line(f"\u00d7 {k}", 40, True, "#2F6FDE"))
            card.setFixedWidth(self._px(200))
            slots.append(card)
        return self._column([
            self._line("Colors", 24, True, "#667085"),
            self._row(chips, 14),
            self._line("Slots", 24, True, "#667085"),
            self._row(slots, 20),
        ], spacing=10)

    def _slot_column(self, slot, color):
        name, val, bg, fg = color
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._line(f"Slot {slot}  (\u00d7 {slot})", 22, False, "#667085"))
        lay.addWidget(self._chip(name, bg, fg, 26), alignment=Qt.AlignCenter)
        lay.addWidget(self._line(f"{val} \u00d7 {slot} = <b>{val * slot}</b>", 26))
        return col, val * slot

    def _ill_example(self, show_solution=True):
        example = [self.COLORS[1], self.COLORS[1], self.COLORS[0]]      # Red, Red, Blue
        values = [color[1] * slot for slot, color in enumerate(example, start=1)]
        total = sum(values)
        instruction = format_battery_instruction([c[1] for c in example])

        card, lay = self._card()
        lay.addWidget(self._line(f"Sum must be <b>{total}</b>", 36, False, "#222"))
        lay.addWidget(self._line(instruction, 34, True, "#0056B3"))
        if show_solution:
            columns = []
            for slot, color in enumerate(example, start=1):
                col, _ = self._slot_column(slot, color)
                columns.append(col)
            lay.addSpacing(self._px(8))
            lay.addWidget(self._row(columns, self._px(34)))
            lay.addWidget(self._line(" + ".join(str(v) for v in values) + f" = <b>{total}</b> &nbsp;\u2713",
                                     30, False, "#2E9E4F"))
        else:
            lay.addSpacing(self._px(10))
            lay.addWidget(self._line("Slot 1 (\u00d7 1) &nbsp;\u00b7&nbsp; Slot 2 (\u00d7 2) &nbsp;\u00b7&nbsp; Slot 3 (\u00d7 3)",
                                     24, False, "#667085"))
            lay.addWidget(self._line("Which order?", 34, True, "#B85C00"))
        card.setMinimumWidth(self._px(900))
        return card

    def _ill_clock(self):
        T, W = TASK_SECONDS_DEFAULT, WARNING_SECONDS
        specs = [
            (f"{T} s", "#111", "", "Countdown starts when the assembly screen appears", "#D5DBE3"),
            (f"{W} s", "#D92D20", "WARNING - FINISH", f"Last {W} seconds: red digits and a blinking warning", "#D92D20"),
            ("0 s", "#D92D20", "ALARM SOUND", "Time is up: an alarm sounds until you hand over", "#D92D20"),
        ]
        cards = []
        for big, col, warn, cap, border in specs:
            card, lay = self._card(border=border)
            lay.addWidget(self._line(big, 60, True, col))
            lay.addWidget(self._line(warn if warn else "&nbsp;", 22, True, "#D92D20"))
            lay.addWidget(self._text(cap, 21, False, "#475467"))
            card.setFixedWidth(self._px(340))
            card.setMinimumHeight(self._px(240))
            cards.append(card)
        return self._row(cards, 26)

    def _ill_handover(self):
        cards = []
        for point, side, rounds, col in [(1, "Left", "1st, 3rd, 5th \u2026 round", "#2F6FDE"),
                                         (2, "Right", "2nd, 4th, 6th \u2026 round", "#2E9E4F")]:
            card, lay = self._card(border=col)
            lay.addWidget(self._chip(f"POINT {point}", col, size=28), alignment=Qt.AlignCenter)
            lay.addWidget(self._line(f"<b>{side}</b> button", 32))
            lay.addWidget(self._line(rounds, 22, False, "#667085"))
            card.setFixedWidth(self._px(420))
            cards.append(card)

        bar = QLabel("Place the workpiece at <b>Point 1</b>. Press <b>Left</b> upon completion.")
        bar.setTextFormat(Qt.RichText)
        bar.setFont(QFont("Helvetica", self._pt(25)))
        bar.setAlignment(Qt.AlignCenter)
        bar.setStyleSheet("color: #222; padding: 10px 20px; background-color: #E4EBF3; border-radius: 6px;")
        return self._column([self._row(cards, 30), bar], spacing=18)

    def _ill_check(self):
        cards = []
        for point, side in ((1, "LEFT"), (2, "RIGHT")):
            card, lay = self._card()
            lay.addWidget(self._line(f"{side} button", 34, True))
            lay.addWidget(self._line(f"Point {point}", 26, False, "#667085"))
            state = self._line("waiting \u2026", 34, True, "#98A2B3")
            lay.addWidget(state)
            card.setFixedWidth(self._px(400))
            card.setMinimumHeight(self._px(190))
            self.check_cards[point] = (card, state)
            cards.append(card)
        self.check_status = self._line("", 28, True, "#2E9E4F")
        return self._column([self._row(cards, 40), self.check_status], spacing=20)

    def _ill_alerts(self):
        def sample_button(text, callback):
            b = QPushButton(text)
            b.setFont(QFont("Helvetica", self._pt(24)))
            b.setFixedHeight(self._px(70))
            b.setMinimumWidth(self._px(300))
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet("QPushButton { background: white; color: #344054; border: 2px solid #C5CCD6; "
                            "border-radius: 12px; } QPushButton:pressed { background: #EAF1FF; }")
            b.clicked.connect(callback)
            return b

        return self._row([
            sample_button("Error tone", lambda: audio_sys.play_participant(incorrect_audio)),
            sample_button("Warning sound", lambda: audio_sys.play_participant(mistake_audio)),
            sample_button("Vest vibration", activate_haptic_vest),
        ], 26)

    def _ill_ready(self):
        R, T = RETRIEVAL_SECONDS, TASK_SECONDS_DEFAULT
        chips = [self._chip(f"Retrieve \u00b7 {R} s", "#2F6FDE", size=26),
                 self._arrow(),
                 self._chip(f"Assemble \u00b7 {T} s", "#2E9E4F", size=26),
                 self._arrow(),
                 self._chip("Hand over", "#B85C00", size=26)]
        return self._column([self._row(chips, 16),
                             self._line("\u21bb  repeat until the practice round ends", 24, False, "#667085")])

    # --------------------------------------------------------------- navigation
    def reset(self):
        self.buttons_seen.clear()
        self._update_check_ui()
        self._show_step(0)
        self.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()

    def _show_step(self, idx, send=True):
        self.current_step = idx
        n = self.pages.count()
        self.pages.setCurrentIndex(idx)
        self.step_counter.setText(f"Step {idx + 1} / {n}")
        self.dots_label.setText(" ".join("\u25cf" if i == idx else "\u25cb" for i in range(n)))
        self.back_button.setEnabled(idx > 0)
        self.next_button.setText("Continue  \u2192" if idx == n - 1 else "Next  \u2192")
        if idx == self.check_step:
            self._update_check_ui()
        if send:
            send_marker(f"Tutorial_Step_{idx + 1}")

    def next_step(self):
        if self.current_step >= self.pages.count() - 1:
            send_marker("Tutorial_Finished")
            self.finish_callback()
        else:
            self._show_step(self.current_step + 1)

    def prev_step(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _update_check_ui(self):
        for point, (card, state) in self.check_cards.items():
            if point in self.buttons_seen:
                card.setStyleSheet("QFrame#card { background-color: #ECFDF3; border: 3px solid #2E9E4F; "
                                   "border-radius: 14px; }")
                state.setText("\u2713 pressed")
                state.setStyleSheet("color: #2E9E4F;")
            else:
                card.setStyleSheet("QFrame#card { background-color: white; border: 3px solid #D5DBE3; "
                                   "border-radius: 14px; }")
                state.setText("waiting \u2026")
                state.setStyleSheet("color: #98A2B3;")
        if len(self.buttons_seen) == 2:
            self.check_status.setText("Both buttons work!  Press the <b>Right</b> button to continue.")
        else:
            self.check_status.setText("")

    def on_point_key(self, point):
        """Hardware buttons: F13 (Left / Point 1) and F14 (Right / Point 2)."""
        if self.current_step == self.check_step:
            both_before = len(self.buttons_seen) == 2
            if both_before:
                if point == 2:
                    self.next_step()
                return
            self.buttons_seen.add(point)
            self._update_check_ui()
            send_marker(f"Tutorial_Button_Check_Point_{point}")
            return
        if point == 2:
            self.next_step()
        else:
            self.prev_step()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self.next_step()
        elif event.key() == Qt.Key_Left:
            self.prev_step()
        else:
            super().keyPressEvent(event)

class trainingdonescreen(QWidget):
    def __init__(self, close_callback):
        super().__init__()
        self.close_callback = close_callback
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(30)

        title = QLabel("Training complete!")
        title.setFont(QFont("Helvetica", 56, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel("Well done.<br><br>If anything is still unclear, please ask the experimenter now.<br>"
                     "The real experiment starts next.")
        msg.setTextFormat(Qt.RichText)
        msg.setFont(QFont("Helvetica", 30))
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        btn = QPushButton("Finish Training")
        btn.setFont(QFont("Helvetica", 28))
        btn.setFixedSize(340, 70)
        btn.clicked.connect(self.close_callback)
        layout.addWidget(btn, alignment=Qt.AlignCenter)
        self.setLayout(layout)

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
        self.pending_training_end = False
        
        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.master_timer_tick)
        
        self.stacked_widget = QStackedWidget()
        self.setup_screen = setupscreen(self.setup_finished_callback)
        self.start_screen = startscreen(self.start_experiment_tracking) 
        self.retrieval_screen = retrievalscreen(self.show_workpiece_task, self.get_current_scenario)
        self.task_screen = workpiecetaskscreen(self.on_handover_complete, self.get_current_scenario)
        self.short_rest_screen = restscreen(self.after_rest_callback)
        self.long_rest_screen = longrestscreen(self.after_rest_callback)
        self.tutorial_screen = tutorialscreen(self.tutorial_finished_callback)
        self.training_done_screen = trainingdonescreen(self.close_training)
        
        self.stacked_widget.addWidget(self.setup_screen)        # 0
        self.stacked_widget.addWidget(self.start_screen)        # 1
        self.stacked_widget.addWidget(self.retrieval_screen)    # 2
        self.stacked_widget.addWidget(self.task_screen)         # 3
        self.stacked_widget.addWidget(self.short_rest_screen)   # 4
        self.stacked_widget.addWidget(self.long_rest_screen)    # 5
        self.stacked_widget.addWidget(self.tutorial_screen)     # 6  (training only)
        self.stacked_widget.addWidget(self.training_done_screen)  # 7  (training only)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)
        
        self.quit_shortcut = QShortcut(QKeySequence("q"), self)
        self.quit_shortcut.activated.connect(QApplication.instance().quit)
        
        self.mistake_shortcut = QShortcut(QKeySequence("F12"), self)
        self.mistake_shortcut.activated.connect(self.trigger_mistake)

        self.f13_shortcut = QShortcut(QKeySequence("F13"), self)
        self.f13_shortcut.activated.connect(lambda: self.on_point_button(1))

        self.f14_shortcut = QShortcut(QKeySequence("F14"), self)
        self.f14_shortcut.activated.connect(lambda: self.on_point_button(2))

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
        
        if current_condition == "training":
            self.begin_training()
        else:
            self.stacked_widget.setCurrentIndex(1)

    # ------------------------------------------------------------------ training
    def begin_training(self):
        """Training = tutorial (screens one by one) + 3 min baseline-like practice."""
        global TRAINING_SEQUENCE
        TRAINING_SEQUENCE = build_training_sequence()
        self.scenarios = ["baseline"]
        self.current_scenario_idx = 0
        self.pending_training_end = False
        self.current_trial = 0

        self.retrieval_screen.training_tag.show()
        self.task_screen.training_tag.show()
        self.start_screen.set_training_mode()

        print("\n" + "=" * 50)
        print(f"TRAINING SESSION: tutorial + {TRAINING_SECONDS} s baseline-like practice "
              f"(markers prefixed '{TRAINING_MARKER_PREFIX}', CSV logging: {LOG_TRAINING_CSV})")
        print("=" * 50 + "\n")

        send_marker("Screen_Tutorial_Start")
        self.tutorial_screen.reset()
        self.stacked_widget.setCurrentIndex(6)
        self.tutorial_screen.setFocus()

    def tutorial_finished_callback(self):
        send_marker("Screen_Tutorial_Finished")
        self.stacked_widget.setCurrentIndex(1)

    def finish_training(self):
        self.master_timer.stop()
        self.pending_training_end = False
        audio_sys.stop_looping_alarm()
        self.task_screen.flush_pending_log()
        send_marker("Training_Complete")
        self.stacked_widget.setCurrentIndex(7)

    def close_training(self):
        send_marker("Training_Closed")
        QApplication.instance().quit()

    def on_point_button(self, point):
        """Hardware buttons F13 / F14: navigate the tutorial or hand over a workpiece."""
        if self.stacked_widget.currentWidget() is self.tutorial_screen:
            self.tutorial_screen.on_point_key(point)
        else:
            self.task_screen.handover_received(point)
        
    def get_current_scenario(self):
        if self.scenarios and self.current_scenario_idx < len(self.scenarios):
            return self.scenarios[self.current_scenario_idx]
        return "baseline"
        
    def start_experiment_tracking(self):
        send_marker("Screen_Start_Instructions")
        if current_condition in ["hard", "manual"]:
            self.scenario_active_seconds = 0
            self.master_timer.start(1000) 
            self.announce_scenario()
        elif current_condition == "training":
            # Baseline-like: no scenario announcement, no cues. Only the 3 min clock.
            self.scenario_active_seconds = 0
            self.master_timer.start(1000)
            send_marker("Training_Practice_Started")
        self.start_trial_cycle()

    def master_timer_tick(self):
        self.scenario_active_seconds += 1
        if current_condition == "training":
            if self.scenario_active_seconds >= TRAINING_SECONDS:
                # Do not cut the participant off mid-assembly: end at the next trial boundary.
                self.pending_training_end = True
                self.master_timer.stop()
            return
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
        if training_active and self.pending_training_end:
            self.finish_training()
            return

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
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_resources)
    
    audio_sys.setup_devices(participant_keyword="Trekz", researcher_keyword="Realtek(R) Audio")
    
    controller = paradigmcontroller()
    
    screens = app.screens()
    if len(screens) > 1:
        second_screen = screens[1]
        controller.move(second_screen.geometry().topLeft())
        controller.show()
        if controller.windowHandle():
            controller.windowHandle().setScreen(second_screen)
        controller.showFullScreen()
    else:
        controller.showFullScreen()
        
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_paradigm()
