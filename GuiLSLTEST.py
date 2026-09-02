# This code runs both the GUI and the robot sequence in a coordinated manner, 
# ensuring that the robot waits for user input before proceeding to the next step. 
# It also handles LSL marker streaming for synchronization with other systems.

import sys
import random
import os
import csv
import time
import math
import winsound
import subprocess
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, 
                             QPushButton, QVBoxLayout, QMessageBox, QStackedWidget,
                             QShortcut, QComboBox, QGridLayout)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence
from pylsl import StreamInfo, StreamOutlet

# dynamically resolve the directory where this script is located
base_dir = os.path.dirname(os.path.abspath(__file__))
correct_audio = os.path.join(base_dir, "correct_answer.wav")
incorrect_audio = os.path.join(base_dir, "incorrect_answer.wav")

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
            
            # if addition is chosen and target > 1 (since 1 can't be made with two positive integers > 0)
            if op == "+" and target > 1:
                a = random.randint(1, target - 1)
                b = target - a
                return f"{a} + {b}"
            else:
                # subtraction (or fallback to subtraction if target is 1)
                b = random.randint(1, 9)
                a = target + b
                return f"{a} - {b}"
        else:
            # easy mode y coordinate: original 3 numbers logic
            a = random.randint(1, 9)
            b = random.randint(1, 9)
            c = a + b - target
            
            # ensure c is within 1 to 9 to keep it at 1 digit
            while c < 1 or c > 9:
                a = random.randint(1, 9)
                b = random.randint(1, 9)
                c = a + b - target
                
            return f"{a} + {b} - {c}"
            
    elif difficulty == "hard":
        # hard mode: custom constraints per operation type
        equation_type = random.choice(["add_sub", "mul_sub", "div_sub"])
        
        if equation_type == "add_sub":
            # sum and rests numbers
            a = random.randint(10, 39)
            b = random.randint(10, 39)
            c = a + b - target
            
            # ensure c also remains within 10 to 39
            while c < 10 or c > 39:
                a = random.randint(10, 39)
                b = random.randint(10, 39)
                c = a + b - target
                
            return f"{a} + {b} - {c}"
            
        elif equation_type == "mul_sub":
            # multiplications numbers between 3 and 12
            a = random.randint(3, 12)
            b = random.randint(3, 12)
            c = (a * b) - target
            
            # regenerate variables if c results in a negative number
            while c < 0:
                a = random.randint(3, 12)
                b = random.randint(3, 12)
                c = (a * b) - target
                
            return f"({a} * {b}) - {c}"
            
        elif equation_type == "div_sub":
            # divisions numbers between 2 and 12 for the base factors
            b = random.randint(2, 12)
            div_val = random.randint(2, 12)
            a = b * div_val
            
            # calculate c so that c - (a / b) equals the target coordinate
            c = target + div_val
                
            return f"{c} - ({a} / {b})"

class setupscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        # store the function that will transition to the start screen
        self.switch_callback = switch_callback
        self.init_ui()
        
    def init_ui(self):
        # configure layout for the initial configuration screen
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(30 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(18 * font_size_multiplier))
        title_font = QFont("Helvetica", int(20 * font_size_multiplier), QFont.Bold)
        
        self.title_label = QLabel("experiment configuration")
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        # subject number dropdown implementation
        self.subj_label = QLabel("subject number:")
        self.subj_label.setFont(main_font)
        self.subj_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subj_label)
        
        self.subj_combo = QComboBox()
        self.subj_combo.setFont(main_font)
        self.subj_combo.setFixedWidth(int(300 * font_size_multiplier))
        # populate the dropdown with standard participant identifier integers
        for i in range(1, 100):
            self.subj_combo.addItem(str(i))
        layout.addWidget(self.subj_combo, alignment=Qt.AlignCenter)
        
        # experimental condition dropdown implementation
        self.cond_label = QLabel("condition:")
        self.cond_label.setFont(main_font)
        self.cond_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cond_label)
        
        self.cond_combo = QComboBox()
        self.cond_combo.setFont(main_font)
        self.cond_combo.setFixedWidth(int(300 * font_size_multiplier))
        self.cond_combo.addItems(["training", "baseline", "easy", "hard"])
        layout.addWidget(self.cond_combo, alignment=Qt.AlignCenter)
        
        # button to save configuration and proceed
        self.continue_button = QPushButton("continue")
        self.continue_button.setFont(main_font)
        self.continue_button.setFixedWidth(int(300 * font_size_multiplier))
        self.continue_button.setFixedHeight(int(70 * font_size_multiplier))
        self.continue_button.clicked.connect(self.save_and_continue)
        layout.addWidget(self.continue_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def save_and_continue(self):
        global difficulty, subject_number, current_condition
        
        # assign dropdown values to global parameters
        subject_number = self.subj_combo.currentText()
        current_condition = self.cond_combo.currentText()
        
        # map the condition string to the underlying equation difficulty logic
        if current_condition == "hard":
            difficulty = "hard"
        else:
            # fallback to easy mathematical structures for training, baseline, and easy conditions
            difficulty = "easy"
            
        send_marker(f"Setup_Complete_Subj_{subject_number}_Cond_{current_condition}_Diff_{difficulty}")
        self.switch_callback()

class startscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        # store the function that will transition to the main task
        self.switch_callback = switch_callback
        self.ticks_left = 30
        
        # initialize a precise timer for the 30-second delay
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.timer_tick)
        
        self.init_ui()
        
    def init_ui(self):
        # configure layout for the start screen
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(40 * font_size_multiplier))
        
        # apply helvetica for readability scaled by the multiplier
        main_font = QFont("Helvetica", int(20 * font_size_multiplier))
        button_font = QFont("Helvetica", int(18 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(48 * font_size_multiplier), QFont.Bold)
        
        # render the introductory text
        intro_text = ("This is the start of the paradigm,<br> you will be given two equations to answer "
                      "<br><br>The results will tell you where in the <b>x, y plane</b> to put the piece you were given <br><br>Have fun")
        
        self.message_label = QLabel(intro_text)
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setContentsMargins(50, 0, 50, 0)
        layout.addWidget(self.message_label)
        
        # label for the countdown timer, initially hidden
        self.countdown_label = QLabel("")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.hide()
        layout.addWidget(self.countdown_label)

        
        # button to proceed
        self.start_button = QPushButton("begin paradigm")
        self.start_button.setFont(button_font)
        self.start_button.setFixedWidth(int(300 * font_size_multiplier))
        self.start_button.setFixedHeight(int(70 * font_size_multiplier))
        
        # connect the click event to our start method
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def on_start_clicked(self):
        global robot_process
        
        send_marker("Robot_Started_Waiting_30s")
        
        # launch the robot script in a non-blocking background process with standard input piped
        robot_process = subprocess.Popen(
            [sys.executable, "robot_sequence.py"],
            stdin=subprocess.PIPE,
            text=True
        )
        
        # update ui to indicate the waiting period
        self.start_button.hide()
        self.message_label.setText("Please take the piece from container I.<br><br>Then wait for the next screen.")
        
        # show and start the countdown
        self.countdown_label.setText(f"{self.ticks_left} s")
        self.countdown_label.show()
        self.timer.start(1000)
        
    def timer_tick(self):
        self.ticks_left -= 1
        
        if self.ticks_left <= 0:
            self.timer.stop()
            # transition to the main task screen once the timer reaches zero
            self.switch_callback()
        else:
            self.countdown_label.setText(f"{self.ticks_left} s")

class intermediatescreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.ticks_left = 0

        # toggle to track which container to display next (true = I, false = II)
        self.container_one_next = True
        
        # initialize position counter to 1
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
        # determine the base time based on the selected difficulty
        if difficulty == "hard":
            base_time = 16
        else:
            base_time = 18
        
        # base time + saved time bonus rounded down to nearest integer second
        total_time = base_time + math.floor(saved_time)

        # determine which container string to use based on the toggle
        container_name = "II" if self.container_one_next else "I"
        
        self.message_label.setText(
            f"Place the workpiece in coordinate <br><b>({x}, {y})</b><br><br>"
            f"Place a new piece in the package and put it back in Position {self.position_counter}<br>"
            f"After placing it, go to <b>container {container_name}</b> to retrieve the next one and come back"
        )
        
        # increment the position counter and wrap around after 4
        self.position_counter += 1
        if self.position_counter > 4:
            self.position_counter = 1
            
        # flip the toggle so it alternates for the next trial
        self.container_one_next = not self.container_one_next

        self.ticks_left = total_time
        self.timer_label.setText(f"{self.ticks_left} s")
        self.timer.start(1000)
        
    def timer_tick(self):
        self.ticks_left -= 1
        
        if self.ticks_left <= 0:
            self.timer.stop()
            # proceed to the next set of equations automatically
            self.switch_callback()
        else:
            self.timer_label.setText(f"{self.ticks_left} s")

class coordinatechallengeapp(QWidget):
    def __init__(self, finish_callback):
        super().__init__()
        self.finish_callback = finish_callback
        
        self.target_x = 0
        self.target_y = 0
        self.time_limit = 15.0
        self.is_red = False
        
        self.attempts = 0
        self.current_eq_x = ""
        self.current_eq_y = ""
        self.start_time = 0.0
        
        # tracking variables for fake error trials
        self.is_fake_error_trial = False
        self.trials_since_last_fake = 0
        self.next_fake_interval = random.randint(2, 5)
        
        # dedicated timer for visual updates every 250 ms
        self.ui_timer = QTimer(self)
        self.ui_timer.setTimerType(Qt.PreciseTimer)
        self.ui_timer.timeout.connect(self.update_ui_tick)
        
        # dedicated single-shot timer to forcibly end the trial
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setTimerType(Qt.PreciseTimer)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.force_time_over)
        
        self.init_ui()
        
    def init_ui(self):
        # use a grid layout as the master layout to ensure perfect centering of the main content
        master_layout = QGridLayout()
        
        # create a central widget and layout for the equations and inputs
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
        
        # place the center widget in the middle column (column 1)
        master_layout.addWidget(center_widget, 0, 1, alignment=Qt.AlignCenter)
        
        # create the exit button
        self.exit_button = QPushButton("exit paradigm")
        self.exit_button.setFont(main_font)
        self.exit_button.setFixedWidth(int(250 * font_size_multiplier))
        self.exit_button.setFixedHeight(int(60 * font_size_multiplier))
        self.exit_button.clicked.connect(QApplication.instance().quit)
        
        # place the exit button in the right column (column 2) and align it to the right and vertical center
        master_layout.addWidget(self.exit_button, 0, 2, alignment=Qt.AlignCenter)
        
        # configure column stretches so columns 0 and 2 take up equal empty space, keeping column 1 perfectly centered
        master_layout.setColumnStretch(0, 1)
        master_layout.setColumnStretch(1, 0)
        master_layout.setColumnStretch(2, 1)
        
        # add a small margin on the right so the button doesn't touch the exact edge of the screen
        master_layout.setContentsMargins(0, 0, 0, 0)
        
        self.setLayout(master_layout)
        
    def save_to_csv(self, time_taken, is_correct):
        # define the target directory dynamically and ensure it exists
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # format the subject number with a leading zero if necessary
        try:
            subj_int = int(subject_number)
            subj_str = f"s{subj_int:02d}"
        except ValueError:
            subj_str = f"s_{subject_number}"
            
        # construct the full file path
        filename = f"{subj_str}_{current_condition}.csv"
        filepath = os.path.join(log_dir, filename)
        
        # check if the file already exists to write headers if needed
        file_exists = os.path.isfile(filepath)
        
        # append the trial results to the csv file
        with open(filepath, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                # added "is_fake_error" to the end of the header row
                writer.writerow(["subject", "condition", "difficulty", "time_taken_s", "correct", "attempts", "equation_x", "equation_y", "is_fake_error"])
            
            # append self.is_fake_error_trial to the data row
            writer.writerow([subject_number, current_condition, difficulty, round(time_taken, 3), is_correct, self.attempts, self.current_eq_x, self.current_eq_y, self.is_fake_error_trial])
            
    def start_challenge(self):
        self.target_x = random.randint(1, 16)
        self.target_y = random.randint(1, 16)
        
        # pass is_x=true so the generator knows to use 2 numbers for x
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
        
        # determine if this trial should force a fake error
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
            
        # send marker indicating the challenge started, tagging fake errors
        if self.is_fake_error_trial:
            send_marker(f"MathTask_Start_Target_X{self.target_x}_Y{self.target_y}_FakeError")
        else:
            send_marker(f"MathTask_Start_Target_X{self.target_x}_Y{self.target_y}")
        
        # start both timers simultaneously
        self.ui_timer.start(250)
        # multiply by 1000 to convert seconds to milliseconds for the single shot
        self.timeout_timer.start(int(self.time_limit * 1000))
        
    def update_ui_tick(self):
        # calculate exact time elapsed for ui logic
        elapsed = time.perf_counter() - self.start_time
        remaining = self.time_limit - elapsed
        
        # safety check: if ui timer fires after timeout, do nothing 
        # (force_time_over will handle it)
        if remaining <= 0:
            return
            
        time_seconds = math.ceil(remaining)
        
        # alternate color rapidly during the last 5 seconds
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
        
        winsound.PlaySound(incorrect_audio, winsound.SND_FILENAME | winsound.SND_ASYNC)
        
        # pass saved_time = 0.0 on timeout
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
                
                # intercept correct answers if this is a fake error trial
                if self.is_fake_error_trial:
                    send_marker(f"MathTask_FakeIncorrect_Attempt_{self.attempts}")
                    self.status_label.setText("incorrect, please try again.")
                    winsound.PlaySound(incorrect_audio, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return
                
                send_marker(f"MathTask_Correct_Attempt_{self.attempts}")
                self.ui_timer.stop()
                self.timeout_timer.stop()
                
                # compute remaining time bonus
                saved_time = max(0.0, self.time_limit - elapsed)
                
                self.save_to_csv(elapsed, True)
                
                # play sound using dynamic path
                winsound.PlaySound(correct_audio, winsound.SND_FILENAME | winsound.SND_ASYNC)
                
                # pass target coordinates along with the saved time reward
                self.finish_callback(self.target_x, self.target_y, saved_time)
            else:
                send_marker(f"MathTask_Incorrect_Attempt_{self.attempts}")
                self.status_label.setText("incorrect, please try again.")
                
                # play the incorrect sound only if the difficulty is set to hard
                if difficulty == "hard":
                    winsound.PlaySound(incorrect_audio, winsound.SND_FILENAME | winsound.SND_ASYNC)
                
        except ValueError:
            send_marker("MathTask_InvalidInput")
            self.status_label.setText("invalid input, please enter integers.")

class paradigmcontroller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("coordinate placement paradigm")
        
        # initialize trial tracking variables
        self.current_trial = 0
        self.max_trials = 10 
        
        self.stacked_widget = QStackedWidget()
        
        # bypass intermediate screen for the very first trial start
        self.setup_screen = setupscreen(self.show_start_screen)
        self.start_screen = startscreen(self.show_main_task) 
        self.intermediate_screen = intermediatescreen(self.show_main_task)
        self.main_task_screen = coordinatechallengeapp(self.show_intermediate_screen)
        
        self.stacked_widget.addWidget(self.setup_screen)
        self.stacked_widget.addWidget(self.start_screen)
        self.stacked_widget.addWidget(self.intermediate_screen)
        self.stacked_widget.addWidget(self.main_task_screen)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)
        
        self.quit_shortcut = QShortcut(QKeySequence("q"), self)
        self.quit_shortcut.activated.connect(QApplication.instance().quit)
        
        send_marker("Screen_Setup")
        
    def show_start_screen(self):
        send_marker("Screen_Start_Instructions")
        # transition from setup screen to the introduction display
        self.stacked_widget.setCurrentIndex(1)
        
    def show_intermediate_screen(self, x, y, saved_time=0.0):
        global robot_process
        
        send_marker(f"Screen_Intermediate_Picking_Piece_Target_X{x}_Y{y}")
        
        # send the continuation signal to the robot when the math task finishes
        if robot_process is not None and robot_process.poll() is None:
            try:
                robot_process.stdin.write("continue\n")
                robot_process.stdin.flush()
            except Exception:
                pass
        # forward coordinates and saved time bonus to transition screen
        self.intermediate_screen.start_transition(x, y, saved_time)
        self.stacked_widget.setCurrentIndex(2)
        
    def show_main_task(self):
        # check if the maximum number of trials has been reached
        if self.current_trial >= self.max_trials:
            send_marker("Experiment_Complete")
            # gracefully exit the application once the experiment is complete
            QApplication.instance().quit()
            return
            
        # increment the trial counter
        self.current_trial += 1
        send_marker(f"Screen_MathTask_Trial_{self.current_trial}")
        
        # generate a new challenge and start the timer immediately
        self.main_task_screen.start_challenge()
        self.stacked_widget.setCurrentIndex(3)

def cleanup_robot_process():
    global robot_process
    send_marker("Application_Closing")
    # check if the process was started and terminate it if it exists
    if robot_process is not None:
        robot_process.terminate()

def run_paradigm():
    init_lsl()
    
    app = QApplication(sys.argv)
    
    # ensure the cleanup function runs whenever the application is instructed to quit
    app.aboutToQuit.connect(cleanup_robot_process)
    
    controller = paradigmcontroller()
    
    # get the list of connected screens
    screens = app.screens()
    
    # check if there is more than one monitor connected
    if len(screens) > 1:
        # index 1 represents the second monitor (index 0 is the main one)
        second_screen = screens[1].geometry()
        
        # move the window to the top-left corner of the second screen
        controller.move(second_screen.left(), second_screen.top())
        
    controller.showFullScreen()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_paradigm()