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
import socket
import bhaptics_python
import sounddevice as sd
import soundfile as sf

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, 
                             QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QStackedWidget,
                             QShortcut, QComboBox, QGridLayout, QCheckBox, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QFont, QKeySequence, QPainter, QBrush, QPen, QColor
from pylsl import StreamInfo, StreamOutlet

base_dir = os.path.dirname(os.path.abspath(__file__))

correct_audio = os.path.join(base_dir, "correct_answer.wav") 
incorrect_audio = os.path.join(base_dir, "incorrect_answer.wav")
alarm_audio = os.path.join(base_dir, "alarm_llm.wav")
if not os.path.exists(alarm_audio):
    alarm_audio = incorrect_audio

mode_audio_haptic = os.path.join(base_dir, "AUDIO_HAPTIC_MODE.wav")
mode_audio_only = os.path.join(base_dir, "AUDIOHELP_mode.wav")
mode_haptic_only = os.path.join(base_dir, "HapticVest_Mode.wav")
mode_robot_fast = os.path.join(base_dir, "ROBOT_FAST_MODE.wav")
mode_robot_slow = os.path.join(base_dir, "ROBOT_SLOW_MODE.wav")
mode_baseline = os.path.join(base_dir, "BASELINE_MODE.wav")

container1_audio = os.path.join(base_dir, "CONTAINER1_ALERT.wav")
container2_audio = os.path.join(base_dir, "CONTAINER2.wav")
mistake_audio = os.path.join(base_dir, "MISTAKE_ALERT.wav")

ROBOT_OWN_IP = "192.168.29.61"
DIFFICULTY_PORT = 50001

marker_outlet = None

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
    full_vest_pattern = [50] * 40
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

font_size_multiplier = 1.6
difficulty = "hard"
subject_number = "1"
current_condition = "training"
active_scenarios_list = []
robot_process = None

# --- 5 Secuencias Fijas y Predefinidas (Idénticas al HTML del Supervisor) ---
SEQUENCES_POOL = {
    "SECUENCIA A": [
        ["Blanco", "Amarillo", "Gris", "Verde", "Rojo"],
        ["Negro", "Verde", "Gris", "Amarillo", "Rojo"],
        ["Amarillo", "Negro", "Blanco", "Rojo", "Verde"],
        ["Negro", "Gris", "Rojo", "Amarillo", "Verde"],
        ["Verde", "Gris", "Blanco", "Negro", "Amarillo"],
        ["Gris", "Amarillo", "Blanco", "Rojo", "Negro"],
        ["Amarillo", "Verde", "Rojo", "Gris", "Blanco"],
        ["Verde", "Gris", "Blanco", "Amarillo", "Negro"],
        ["Rojo", "Negro", "Verde", "Gris", "Amarillo"],
        ["Negro", "Gris", "Rojo", "Amarillo", "Verde"],
        ["Verde", "Gris", "Negro", "Amarillo", "Blanco"],
        ["Negro", "Gris", "Rojo", "Verde", "Amarillo"],
        ["Blanco", "Negro", "Gris", "Amarillo", "Rojo"],
        ["Negro", "Rojo", "Blanco", "Gris", "Amarillo"],
        ["Gris", "Blanco", "Rojo", "Verde", "Amarillo"],
        ["Verde", "Blanco", "Gris", "Negro", "Amarillo"],
        ["Amarillo", "Gris", "Negro", "Blanco", "Rojo"],
        ["Rojo", "Amarillo", "Blanco", "Verde", "Gris"],
        ["Gris", "Negro", "Amarillo", "Blanco", "Rojo"],
        ["Negro", "Blanco", "Amarillo", "Rojo", "Gris"],
        ["Verde", "Gris", "Negro", "Amarillo", "Blanco"],
        ["Negro", "Amarillo", "Rojo", "Verde", "Gris"],
        ["Negro", "Verde", "Blanco", "Amarillo", "Gris"],
        ["Verde", "Amarillo", "Blanco", "Rojo", "Gris"],
        ["Verde", "Amarillo", "Gris", "Blanco", "Rojo"],
        ["Blanco", "Gris", "Amarillo", "Rojo", "Verde"],
        ["Gris", "Blanco", "Rojo", "Verde", "Amarillo"],
        ["Gris", "Blanco", "Rojo", "Negro", "Verde"],
        ["Blanco", "Gris", "Rojo", "Amarillo", "Verde"],
        ["Rojo", "Amarillo", "Negro", "Blanco", "Gris"],
        ["Amarillo", "Gris", "Blanco", "Verde", "Rojo"],
        ["Verde", "Blanco", "Amarillo", "Negro", "Gris"],
        ["Rojo", "Gris", "Verde", "Amarillo", "Negro"],
        ["Gris", "Verde", "Blanco", "Negro", "Rojo"],
        ["Verde", "Blanco", "Negro", "Rojo", "Gris"],
        ["Amarillo", "Blanco", "Gris", "Verde", "Negro"],
        ["Rojo", "Gris", "Negro", "Blanco", "Verde"],
        ["Rojo", "Negro", "Verde", "Blanco", "Gris"],
        ["Negro", "Verde", "Blanco", "Rojo", "Gris"],
        ["Gris", "Rojo", "Negro", "Verde", "Amarillo"],
        ["Negro", "Rojo", "Amarillo", "Verde", "Gris"],
        ["Blanco", "Negro", "Verde", "Amarillo", "Gris"]
    ],
    "SECUENCIA B": [
        ["Blanco", "Amarillo", "Gris", "Verde", "Negro"],
        ["Negro", "Amarillo", "Gris", "Blanco", "Verde"],
        ["Amarillo", "Verde", "Rojo", "Negro", "Blanco"],
        ["Blanco", "Negro", "Amarillo", "Gris", "Verde"],
        ["Verde", "Rojo", "Gris", "Negro", "Blanco"],
        ["Rojo", "Gris", "Negro", "Amarillo", "Verde"],
        ["Amarillo", "Negro", "Blanco", "Verde", "Gris"],
        ["Verde", "Rojo", "Negro", "Gris", "Blanco"],
        ["Amarillo", "Negro", "Rojo", "Blanco", "Verde"],
        ["Blanco", "Verde", "Rojo", "Amarillo", "Gris"],
        ["Verde", "Negro", "Gris", "Rojo", "Amarillo"],
        ["Blanco", "Rojo", "Negro", "Verde", "Gris"],
        ["Blanco", "Rojo", "Amarillo", "Negro", "Verde"],
        ["Negro", "Gris", "Amarillo", "Blanco", "Verde"],
        ["Verde", "Blanco", "Negro", "Rojo", "Amarillo"],
        ["Verde", "Rojo", "Amarillo", "Blanco", "Negro"],
        ["Gris", "Amarillo", "Negro", "Verde", "Blanco"],
        ["Negro", "Verde", "Amarillo", "Gris", "Rojo"],
        ["Gris", "Negro", "Verde", "Amarillo", "Blanco"],
        ["Rojo", "Negro", "Blanco", "Gris", "Verde"],
        ["Verde", "Negro", "Amarillo", "Rojo", "Gris"],
        ["Verde", "Rojo", "Blanco", "Gris", "Negro"],
        ["Gris", "Negro", "Rojo", "Amarillo", "Verde"],
        ["Blanco", "Rojo", "Negro", "Amarillo", "Verde"],
        ["Rojo", "Negro", "Amarillo", "Gris", "Blanco"],
        ["Blanco", "Rojo", "Amarillo", "Gris", "Negro"],
        ["Gris", "Negro", "Blanco", "Amarillo", "Rojo"],
        ["Negro", "Gris", "Verde", "Amarillo", "Blanco"],
        ["Gris", "Amarillo", "Rojo", "Blanco", "Negro"],
        ["Rojo", "Gris", "Negro", "Verde", "Amarillo"],
        ["Rojo", "Amarillo", "Verde", "Blanco", "Gris"],
        ["Negro", "Gris", "Verde", "Rojo", "Amarillo"],
        ["Negro", "Verde", "Blanco", "Gris", "Rojo"],
        ["Negro", "Rojo", "Gris", "Blanco", "Amarillo"],
        ["Verde", "Amarillo", "Negro", "Gris", "Rojo"],
        ["Amarillo", "Verde", "Rojo", "Blanco", "Negro"],
        ["Rojo", "Gris", "Negro", "Amarillo", "Blanco"],
        ["Verde", "Gris", "Amarillo", "Negro", "Rojo"],
        ["Negro", "Verde", "Amarillo", "Gris", "Blanco"],
        ["Rojo", "Gris", "Negro", "Amarillo", "Verde"],
        ["Gris", "Negro", "Rojo", "Verde", "Amarillo"],
        ["Blanco", "Negro", "Verde", "Amarillo", "Gris"]
    ],
    "SECUENCIA C": [
        ["Blanco", "Amarillo", "Negro", "Rojo", "Verde"],
        ["Negro", "Blanco", "Amarillo", "Gris", "Rojo"],
        ["Gris", "Amarillo", "Verde", "Negro", "Rojo"],
        ["Negro", "Amarillo", "Gris", "Verde", "Rojo"],
        ["Verde", "Blanco", "Amarillo", "Gris", "Negro"],
        ["Gris", "Amarillo", "Negro", "Blanco", "Rojo"],
        ["Amarillo", "Blanco", "Rojo", "Gris", "Negro"],
        ["Rojo", "Negro", "Verde", "Gris", "Blanco"],
        ["Rojo", "Amarillo", "Gris", "Negro", "Verde"],
        ["Blanco", "Verde", "Amarillo", "Gris", "Negro"],
        ["Amarillo", "Gris", "Negro", "Rojo", "Blanco"],
        ["Rojo", "Gris", "Blanco", "Amarillo", "Negro"],
        ["Blanco", "Gris", "Verde", "Rojo", "Negro"],
        ["Amarillo", "Blanco", "Negro", "Verde", "Gris"],
        ["Gris", "Negro", "Amarillo", "Blanco", "Rojo"],
        ["Blanco", "Negro", "Amarillo", "Verde", "Gris"],
        ["Negro", "Verde", "Blanco", "Gris", "Amarillo"],
        ["Amarillo", "Negro", "Gris", "Blanco", "Verde"],
        ["Negro", "Blanco", "Verde", "Rojo", "Gris"],
        ["Negro", "Verde", "Gris", "Rojo", "Amarillo"],
        ["Blanco", "Negro", "Amarillo", "Rojo", "Verde"],
        ["Verde", "Blanco", "Negro", "Gris", "Amarillo"],
        ["Gris", "Negro", "Rojo", "Amarillo", "Blanco"],
        ["Verde", "Rojo", "Negro", "Gris", "Blanco"],
        ["Verde", "Amarillo", "Blanco", "Gris", "Rojo"],
        ["Blanco", "Gris", "Verde", "Rojo", "Amarillo"],
        ["Verde", "Gris", "Blanco", "Rojo", "Amarillo"],
        ["Negro", "Amarillo", "Gris", "Rojo", "Blanco"],
        ["Negro", "Rojo", "Amarillo", "Blanco", "Verde"],
        ["Rojo", "Negro", "Gris", "Blanco", "Verde"],
        ["Amarillo", "Rojo", "Verde", "Negro", "Gris"],
        ["Verde", "Gris", "Negro", "Rojo", "Amarillo"],
        ["Rojo", "Amarillo", "Gris", "Blanco", "Negro"],
        ["Rojo", "Negro", "Amarillo", "Gris", "Verde"],
        ["Verde", "Blanco", "Amarillo", "Negro", "Gris"],
        ["Negro", "Blanco", "Rojo", "Gris", "Amarillo"],
        ["Rojo", "Negro", "Gris", "Verde", "Amarillo"],
        ["Rojo", "Amarillo", "Gris", "Verde", "Negro"],
        ["Verde", "Rojo", "Gris", "Blanco", "Negro"],
        ["Verde", "Blanco", "Negro", "Rojo", "Gris"],
        ["Amarillo", "Negro", "Blanco", "Verde", "Gris"],
        ["Verde", "Gris", "Rojo", "Blanco", "Negro"]
    ],
    "SECUENCIA D": [
        ["Verde", "Amarillo", "Gris", "Negro", "Rojo"],
        ["Amarillo", "Blanco", "Negro", "Verde", "Rojo"],
        ["Verde", "Negro", "Gris", "Rojo", "Blanco"],
        ["Amarillo", "Rojo", "Blanco", "Negro", "Gris"],
        ["Verde", "Blanco", "Gris", "Negro", "Rojo"],
        ["Negro", "Rojo", "Verde", "Gris", "Amarillo"],
        ["Amarillo", "Gris", "Blanco", "Verde", "Negro"],
        ["Blanco", "Negro", "Rojo", "Amarillo", "Gris"],
        ["Rojo", "Amarillo", "Blanco", "Gris", "Negro"],
        ["Blanco", "Verde", "Rojo", "Gris", "Negro"],
        ["Negro", "Gris", "Rojo", "Verde", "Blanco"],
        ["Amarillo", "Verde", "Blanco", "Gris", "Negro"],
        ["Blanco", "Gris", "Negro", "Verde", "Rojo"],
        ["Amarillo", "Negro", "Gris", "Verde", "Blanco"],
        ["Rojo", "Negro", "Verde", "Amarillo", "Gris"],
        ["Blanco", "Amarillo", "Gris", "Rojo", "Verde"],
        ["Rojo", "Negro", "Gris", "Blanco", "Verde"],
        ["Amarillo", "Negro", "Verde", "Gris", "Blanco"],
        ["Blanco", "Negro", "Gris", "Rojo", "Amarillo"],
        ["Rojo", "Amarillo", "Blanco", "Negro", "Gris"],
        ["Verde", "Rojo", "Blanco", "Negro", "Amarillo"],
        ["Verde", "Amarillo", "Gris", "Negro", "Rojo"],
        ["Rojo", "Gris", "Amarillo", "Negro", "Blanco"],
        ["Rojo", "Verde", "Negro", "Gris", "Blanco"],
        ["Verde", "Blanco", "Rojo", "Negro", "Amarillo"],
        ["Blanco", "Gris", "Verde", "Negro", "Amarillo"],
        ["Verde", "Negro", "Amarillo", "Rojo", "Blanco"],
        ["Gris", "Amarillo", "Rojo", "Blanco", "Verde"],
        ["Gris", "Negro", "Rojo", "Amarillo", "Verde"],
        ["Negro", "Amarillo", "Blanco", "Rojo", "Gris"],
        ["Blanco", "Amarillo", "Verde", "Gris", "Negro"],
        ["Negro", "Rojo", "Blanco", "Verde", "Amarillo"],
        ["Rojo", "Gris", "Blanco", "Amarillo", "Verde"],
        ["Blanco", "Amarillo", "Negro", "Verde", "Gris"],
        ["Verde", "Amarillo", "Negro", "Blanco", "Gris"],
        ["Amarillo", "Gris", "Verde", "Rojo", "Negro"],
        ["Rojo", "Negro", "Amarillo", "Verde", "Gris"],
        ["Negro", "Rojo", "Verde", "Blanco", "Amarillo"],
        ["Negro", "Rojo", "Blanco", "Amarillo", "Gris"],
        ["Verde", "Blanco", "Gris", "Amarillo", "Negro"],
        ["Verde", "Amarillo", "Negro", "Gris", "Blanco"],
        ["Blanco", "Negro", "Amarillo", "Rojo", "Gris"]
    ],
    "SECUENCIA E": [
        ["Blanco", "Verde", "Negro", "Rojo", "Amarillo"],
        ["Negro", "Blanco", "Amarillo", "Rojo", "Verde"],
        ["Amarillo", "Rojo", "Negro", "Gris", "Verde"],
        ["Negro", "Gris", "Blanco", "Rojo", "Verde"],
        ["Verde", "Rojo", "Gris", "Amarillo", "Negro"],
        ["Gris", "Amarillo", "Negro", "Rojo", "Blanco"],
        ["Amarillo", "Rojo", "Verde", "Gris", "Blanco"],
        ["Verde", "Blanco", "Rojo", "Gris", "Amarillo"],
        ["Rojo", "Negro", "Amarillo", "Verde", "Blanco"],
        ["Blanco", "Verde", "Rojo", "Negro", "Amarillo"],
        ["Amarillo", "Gris", "Blanco", "Verde", "Rojo"],
        ["Rojo", "Amarillo", "Gris", "Verde", "Negro"],
        ["Blanco", "Rojo", "Negro", "Amarillo", "Gris"],
        ["Amarillo", "Negro", "Rojo", "Blanco", "Gris"],
        ["Gris", "Blanco", "Negro", "Rojo", "Amarillo"],
        ["Blanco", "Gris", "Verde", "Rojo", "Negro"],
        ["Negro", "Verde", "Blanco", "Amarillo", "Rojo"],
        ["Amarillo", "Negro", "Gris", "Rojo", "Blanco"],
        ["Negro", "Rojo", "Blanco", "Amarillo", "Verde"],
        ["Negro", "Amarillo", "Gris", "Blanco", "Verde"],
        ["Blanco", "Amarillo", "Negro", "Gris", "Verde"],
        ["Verde", "Amarillo", "Blanco", "Rojo", "Negro"],
        ["Gris", "Negro", "Blanco", "Amarillo", "Rojo"],
        ["Verde", "Amarillo", "Gris", "Rojo", "Blanco"],
        ["Verde", "Negro", "Gris", "Rojo", "Amarillo"],
        ["Blanco", "Rojo", "Amarillo", "Verde", "Gris"],
        ["Verde", "Gris", "Blanco", "Amarillo", "Negro"],
        ["Negro", "Amarillo", "Gris", "Verde", "Rojo"],
        ["Gris", "Amarillo", "Blanco", "Negro", "Verde"],
        ["Rojo", "Amarillo", "Negro", "Gris", "Blanco"],
        ["Amarillo", "Blanco", "Rojo", "Gris", "Verde"],
        ["Negro", "Rojo", "Amarillo", "Gris", "Verde"],
        ["Rojo", "Amarillo", "Verde", "Negro", "Blanco"],
        ["Negro", "Rojo", "Verde", "Blanco", "Gris"],
        ["Verde", "Blanco", "Amarillo", "Negro", "Rojo"],
        ["Negro", "Blanco", "Rojo", "Gris", "Verde"],
        ["Rojo", "Gris", "Verde", "Blanco", "Negro"],
        ["Rojo", "Amarillo", "Negro", "Verde", "Blanco"],
        ["Negro", "Rojo", "Blanco", "Amarillo", "Verde"],
        ["Verde", "Blanco", "Gris", "Amarillo", "Rojo"],
        ["Verde", "Amarillo", "Blanco", "Rojo", "Negro"],
        ["Blanco", "Negro", "Amarillo", "Rojo", "Verde"]
    ]
}

selected_sequence_id = "SECUENCIA A"
selected_sequence_patterns = SEQUENCES_POOL["SECUENCIA A"]

def get_equation_for_target(target, is_x=False):
    if difficulty == "easy":
        if is_x:
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
            a = random.randint(1, 9)
            b = random.randint(1, 9)
            c = a + b - target
            while c < 1 or c > 9:
                a = random.randint(1, 9)
                b = random.randint(1, 9)
                c = a + b - target
            return f"{a} + {b} - {c}"
            
    elif difficulty == "hard":
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

# --- Canvas de Dibujo Vectorial para 5 Bloques Lego con Color ---
class LegoAssemblyWidget(QWidget):
    COLOR_MAP = {
        "verde":    QColor("#2E7D32"),
        "rojo":     QColor("#D32F2F"),
        "amarillo": QColor("#FBC02D"),
        "negro":    QColor("#212121"),
        "gris":     QColor("#757575"),
        "blanco":   QColor("#ECEFF1"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pattern = []
        self.setFixedSize(int(360 * font_size_multiplier), int(290 * font_size_multiplier))

    def set_pattern(self, pattern):
        self.pattern = [c.lower() for c in pattern]
        self.update()

    def paintEvent(self, event):
        if not self.pattern:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        brick_w = 150 * (font_size_multiplier / 1.6)
        brick_h = 42 * (font_size_multiplier / 1.6)
        stud_r = 7 * (font_size_multiplier / 1.6)
        stud_h = 6 * (font_size_multiplier / 1.6)

        center_x = self.width() / 2
        base_y = self.height() - 20

        for layer_idx, color_name in enumerate(self.pattern):
            fill_color = self.COLOR_MAP.get(color_name, QColor("gray"))
            border_color = fill_color.darker(140) if color_name != "negro" else QColor("#424242")

            bx = center_x - (brick_w / 2)
            by = base_y - ((layer_idx + 1) * brick_h)

            # Bloque rectangular
            painter.setPen(QPen(border_color, 2))
            painter.setBrush(QBrush(fill_color))
            painter.drawRoundedRect(QRectF(bx, by, brick_w, brick_h), 4, 4)

            # Studs superiores
            stud_brush = QBrush(fill_color.lighter(120) if color_name != "blanco" else QColor("#CFD8DC"))
            painter.setBrush(stud_brush)
            for s in range(4):
                sx = bx + 16 + s * (brick_w - 32) / 3
                sy = by - stud_h
                painter.drawRoundedRect(QRectF(sx - stud_r, sy, stud_r * 2, stud_h + 1), 2, 2)

class setupscreen(QWidget):
    def __init__(self, switch_callback):
        super().__init__()
        self.switch_callback = switch_callback
        self.scenario_checkboxes = {}
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(20 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(18 * font_size_multiplier))
        title_font = QFont("Helvetica", int(20 * font_size_multiplier), QFont.Bold)
        
        self.title_label = QLabel("Configuración del Experimento")
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)
        
        self.subj_label = QLabel("Número de Sujeto:")
        self.subj_label.setFont(main_font)
        layout.addWidget(self.subj_label, alignment=Qt.AlignCenter)
        
        self.subj_combo = QComboBox()
        self.subj_combo.setFont(main_font)
        self.subj_combo.setFixedWidth(int(300 * font_size_multiplier))
        for i in range(1, 100):
            self.subj_combo.addItem(str(i))
        layout.addWidget(self.subj_combo, alignment=Qt.AlignCenter)
        
        self.cond_label = QLabel("Condición:")
        self.cond_label.setFont(main_font)
        layout.addWidget(self.cond_label, alignment=Qt.AlignCenter)
        
        self.cond_combo = QComboBox()
        self.cond_combo.setFont(main_font)
        self.cond_combo.setFixedWidth(int(300 * font_size_multiplier))
        self.cond_combo.addItems(["training", "baseline", "easy", "hard", "manual"])
        self.cond_combo.currentTextChanged.connect(self.on_condition_changed)
        layout.addWidget(self.cond_combo, alignment=Qt.AlignCenter)
        
        self.scenario_group = QGroupBox("Seleccionar Escenarios (Solo Modo Manual)")
        self.scenario_group.setFont(main_font)
        scenario_layout = QGridLayout()
        
        scenarios = ["audio", "haptic", "audio_haptic", "robot_fast", "robot_slow", "baseline"]
        for i, sc in enumerate(scenarios):
            cb = QCheckBox(sc)
            cb.setFont(main_font)
            cb.setChecked(True)
            self.scenario_checkboxes[sc] = cb
            scenario_layout.addWidget(cb, i // 2, i % 2)
            
        self.scenario_group.setLayout(scenario_layout)
        self.scenario_group.setEnabled(False)
        layout.addWidget(self.scenario_group, alignment=Qt.AlignCenter)
        
        self.continue_button = QPushButton("Continuar")
        self.continue_button.setFont(main_font)
        self.continue_button.setFixedWidth(int(300 * font_size_multiplier))
        self.continue_button.setFixedHeight(int(70 * font_size_multiplier))
        self.continue_button.clicked.connect(self.save_and_continue)
        layout.addWidget(self.continue_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def on_condition_changed(self, text):
        self.scenario_group.setEnabled(text == "manual")
        
    def save_and_continue(self):
        global difficulty, subject_number, current_condition, active_scenarios_list, selected_sequence_id, selected_sequence_patterns
        
        subject_number = self.subj_combo.currentText()
        current_condition = self.cond_combo.currentText()
        
        # Selección aleatoria de una de las 5 secuencias preestablecidas
        selected_sequence_id = random.choice(list(SEQUENCES_POOL.keys()))
        selected_sequence_patterns = SEQUENCES_POOL[selected_sequence_id]
        
        if current_condition == "hard":
            difficulty = "hard"
            active_scenarios_list = ["audio", "haptic", "audio_haptic", "robot_fast", "robot_slow", "baseline"]
        elif current_condition == "manual":
            difficulty = "hard"
            active_scenarios_list = [sc for sc, cb in self.scenario_checkboxes.items() if cb.isChecked()]
            if not active_scenarios_list:
                QMessageBox.warning(self, "Error", "Seleccione al menos un escenario en modo manual.")
                return
        else:
            difficulty = "easy"
            active_scenarios_list = ["baseline"]
            
        send_marker(f"Setup_Complete_Subj_{subject_number}_Cond_{current_condition}_Seq_{selected_sequence_id}")
        self.switch_callback()

class startscreen(QWidget):
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
        layout.setSpacing(int(30 * font_size_multiplier))
        
        main_font = QFont("Helvetica", int(20 * font_size_multiplier))
        button_font = QFont("Helvetica", int(18 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(48 * font_size_multiplier), QFont.Bold)
        alert_font = QFont("Helvetica", int(24 * font_size_multiplier), QFont.Bold)
        
        intro_text = ("<b>Inicio del Paradigma</b><br><br>"
                      "1. Toma las piezas del Contenedor I o II (20s).<br>"
                      "2. Resuelve la ecuación en pantalla (15s).<br>"
                      "3. Ensambla la figura de 5 piezas Lego mostrada.<br><br>"
                      "Presiona <b>F13</b> para Punto 1 (Izquierda)<br>"
                      "Presiona <b>F14</b> para Punto 2 (Derecha)")
        
        self.message_label = QLabel(intro_text)
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        
        self.seq_display_label = QLabel("")
        self.seq_display_label.setFont(alert_font)
        self.seq_display_label.setStyleSheet("color: #D32F2F;")
        self.seq_display_label.setAlignment(Qt.AlignCenter)
        self.seq_display_label.hide()
        layout.addWidget(self.seq_display_label)
        
        self.countdown_label = QLabel("")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.hide()
        layout.addWidget(self.countdown_label)

        self.start_button = QPushButton("Comenzar Paradigma")
        self.start_button.setFont(button_font)
        self.start_button.setFixedWidth(int(300 * font_size_multiplier))
        self.start_button.setFixedHeight(int(70 * font_size_multiplier))
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)
        
    def on_start_clicked(self):
        global robot_process
        send_marker(f"Robot_Started_Waiting_30s_{selected_sequence_id}")
        
        print("\n" + "#"*60)
        print(f"--> REGISTRO: UTILIZAR LA HOJA DE '{selected_sequence_id}' <--")
        print("#"*60 + "\n")
        
        self.seq_display_label.setText(f"HOJA DE REGISTRO: {selected_sequence_id}")
        self.seq_display_label.show()
        
        robot_process = subprocess.Popen(
            [sys.executable, "robot_sequence.py"],
            stdin=subprocess.PIPE,
            text=True
        )
        
        self.start_button.hide()
        self.message_label.setText("Preparando los componentes experimentales...<br>Anota la secuencia en tu hoja de registro.")
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
        
        self.message_label = QLabel("¡Gran trabajo! Toma un breve descanso.<br><br>El siguiente escenario comenzará pronto.")
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        self.countdown_label = QLabel("30 s")
        self.countdown_label.setFont(timer_font)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.countdown_label)
        self.setLayout(layout)
        
    def start_rest(self):
        send_marker("Screen_Short_Rest_Started")
        self.ticks_left = 30
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
        
        self.message_label = QLabel("Has completado un bloque de 3 escenarios.<br><br>Toma un descanso más largo.<br>Presiona el botón cuando estés listo para continuar.")
        self.message_label.setFont(main_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        self.resume_button = QPushButton("Continuar Mediciones")
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
        self.ticks_left = 20
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

        self.timer_label = QLabel("20 s")
        self.timer_label.setFont(timer_font)
        self.timer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.timer_label)

        self.setLayout(layout)

    def start_retrieval(self):
        self.ticks_left = 20
        target_container = "I" if self.container_toggle else "II"
        self.instruction_label.setText(f"Toma las piezas del <b>Contenedor {target_container}</b>")
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

class assemblyscreen(QWidget):
    def __init__(self, finish_callback, get_scenario_cb):
        super().__init__()
        self.finish_callback = finish_callback
        self.get_scenario_cb = get_scenario_cb
        self.ticks_left = 10
        self.active_collection_pt = None
        self.alarm_triggered = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(int(15 * font_size_multiplier))

        header_font = QFont("Helvetica", int(22 * font_size_multiplier), QFont.Bold)
        label_font = QFont("Helvetica", int(18 * font_size_multiplier))
        timer_font = QFont("Helvetica", int(45 * font_size_multiplier), QFont.Bold)

        self.header_label = QLabel("Ensamblar Pieza (5 Bloques)")
        self.header_label.setFont(header_font)
        self.header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.header_label)

        self.lego_canvas = LegoAssemblyWidget(self)
        layout.addWidget(self.lego_canvas, alignment=Qt.AlignCenter)

        self.pt_label = QLabel("")
        self.pt_label.setFont(label_font)
        self.pt_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.pt_label)

        self.timer_label = QLabel("10 s")
        self.timer_label.setFont(timer_font)
        self.timer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.timer_label)

        self.setLayout(layout)

    def start_assembly(self, target_pt, pattern):
        self.active_collection_pt = target_pt
        self.alarm_triggered = False
        
        self.lego_canvas.set_pattern(pattern)

        scenario = self.get_scenario_cb()
        if scenario == "robot_fast":
            self.ticks_left = 8
        elif scenario == "robot_slow":
            self.ticks_left = 12
        else:
            self.ticks_left = 10

        pt_name = "Punto 1 (Izquierda)" if self.active_collection_pt == 1 else "Punto 2 (Derecha)"
        key_hint = "F13" if self.active_collection_pt == 1 else "F14"

        self.pt_label.setText(
            f"Coloca la pieza en <b>{pt_name}</b>.<br>"
            f"Presiona <b>{key_hint}</b> para indicar al robot que la recoja."
        )
        self.timer_label.setStyleSheet("color: black;")
        self.timer_label.setText(f"{self.ticks_left} s")
        send_marker(f"Assembly_Phase_Started_TargetPt_{self.active_collection_pt}_Pattern_{'-'.join(pattern)}")
        self.timer.start(1000)

    def timer_tick(self):
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.timer_label.setText("0 s")
            self.timer_label.setStyleSheet("color: red;")
            if not self.alarm_triggered:
                self.alarm_triggered = True
                send_marker("Assembly_Overtime_Alarm_Started")
                audio_sys.start_looping_alarm(alarm_audio)
        else:
            self.timer_label.setText(f"{self.ticks_left} s")

    def handover_received(self, point_pressed):
        if self.active_collection_pt is None or point_pressed != self.active_collection_pt:
            return
        
        self.timer.stop()
        if self.alarm_triggered:
            audio_sys.stop_looping_alarm()
            send_marker("Assembly_Overtime_Alarm_Stopped")

        send_marker(f"Handover_Confirmed_Point_{point_pressed}")
        self.finish_callback(point_pressed)
        self.active_collection_pt = None

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
        self.ui_timer.timeout.connect(self.update_ui_tick)
        
        self.timeout_timer = QTimer(self)
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
        
        self.instructions_label = QLabel("Calcula las coordenadas (1 a 16).")
        self.instructions_label.setFont(title_font)
        self.instructions_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.instructions_label)
        
        self.x_equation_label = QLabel("")
        self.x_equation_label.setFont(main_font)
        self.x_equation_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.x_equation_label)
        
        self.x_entry = QLineEdit()
        self.x_entry.setFont(main_font)
        self.x_entry.setAlignment(Qt.AlignCenter)
        self.x_entry.setPlaceholderText("Coordenada X")
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
        self.y_entry.setPlaceholderText("Coordenada Y")
        self.y_entry.setFixedWidth(int(250 * font_size_multiplier))
        self.y_entry.setFixedHeight(int(50 * font_size_multiplier))
        center_layout.addWidget(self.y_entry, alignment=Qt.AlignCenter)
        
        self.status_label = QLabel("")
        self.status_label.setFont(main_font)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: red;")
        center_layout.addWidget(self.status_label)
        
        self.submit_button = QPushButton("Comprobar")
        self.submit_button.setFont(main_font)
        self.submit_button.setFixedWidth(int(250 * font_size_multiplier))
        self.submit_button.setFixedHeight(int(60 * font_size_multiplier))
        self.submit_button.clicked.connect(self.check_answer)
        center_layout.addWidget(self.submit_button, alignment=Qt.AlignCenter)
        
        self.timer_text_label = QLabel("Tiempo restante:")
        self.timer_text_label.setFont(title_font)
        self.timer_text_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.timer_text_label)
        
        self.timer_value_label = QLabel("15 s")
        self.timer_value_label.setFont(time_value_font)
        self.timer_value_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.timer_value_label)
        
        master_layout.addWidget(center_widget, 0, 1, alignment=Qt.AlignCenter)
        
        self.exit_button = QPushButton("Salir")
        self.exit_button.setFont(main_font)
        self.exit_button.setFixedWidth(int(250 * font_size_multiplier))
        self.exit_button.setFixedHeight(int(60 * font_size_multiplier))
        self.exit_button.clicked.connect(QApplication.instance().quit)
        
        master_layout.addWidget(self.exit_button, 0, 2, alignment=Qt.AlignCenter)
        master_layout.setColumnStretch(0, 1)
        master_layout.setColumnStretch(1, 0)
        master_layout.setColumnStretch(2, 1)
        
        self.setLayout(master_layout)
        
    def save_to_csv(self, time_taken, is_correct, current_pattern_str=""):
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
                writer.writerow(["subject", "condition", "difficulty", "sequence_id", "time_taken_s", "correct", "attempts", "equation_x", "equation_y", "is_fake_error", "lego_pattern"])
            writer.writerow([subject_number, current_condition, difficulty, selected_sequence_id, round(time_taken, 3), is_correct, self.attempts, self.current_eq_x, self.current_eq_y, self.is_fake_error_trial, current_pattern_str])

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
        
        self.x_equation_label.setText(f"Ecuación X:  {eq_x}")
        self.y_equation_label.setText(f"Ecuación Y:  {eq_y}")
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
        self.finish_callback()
        
    def check_answer(self):
        elapsed = time.perf_counter() - self.start_time
        if elapsed >= self.time_limit:
            return
            
        try:
            user_x = int(self.x_entry.text())
            user_y = int(self.y_entry.text())
            
            if not (1 <= user_x <= 16) or not (1 <= user_y <= 16):
                send_marker("MathTask_InvalidBounds")
                self.status_label.setText("Coordenadas deben ser entre 1 y 16.")
                return
                
            self.attempts += 1
            
            if user_x == self.target_x and user_y == self.target_y:
                if self.is_fake_error_trial:
                    send_marker(f"MathTask_FakeIncorrect_Attempt_{self.attempts}")
                    self.status_label.setText("Incorrecto, intenta de nuevo.")
                    self.play_feedback_audio(is_correct=False)
                    return
                
                send_marker(f"MathTask_Correct_Attempt_{self.attempts}")
                self.ui_timer.stop()
                self.timeout_timer.stop()
                
                self.save_to_csv(elapsed, True)
                self.play_feedback_audio(is_correct=True)
                self.finish_callback()
            else:
                send_marker(f"MathTask_Incorrect_Attempt_{self.attempts}")
                self.status_label.setText("Incorrecto, intenta de nuevo.")
                if difficulty == "hard":
                    self.play_feedback_audio(is_correct=False)
                
        except ValueError:
            send_marker("MathTask_InvalidInput")
            self.status_label.setText("Entrada inválida.")

class paradigmcontroller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paradigma de Ensamble y Colaboración")
        self.current_trial = 0
        self.max_trials = 10 
        
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
        self.retrieval_screen = retrievalscreen(self.show_math_task, self.get_current_scenario)
        self.main_task_screen = coordinatechallengeapp(self.show_assembly_task, self.get_current_scenario)
        self.assembly_screen = assemblyscreen(self.on_handover_complete, self.get_current_scenario)
        self.short_rest_screen = restscreen(self.after_rest_callback)
        self.long_rest_screen = longrestscreen(self.after_rest_callback)
        
        self.stacked_widget.addWidget(self.setup_screen)        # 0
        self.stacked_widget.addWidget(self.start_screen)        # 1
        self.stacked_widget.addWidget(self.retrieval_screen)    # 2
        self.stacked_widget.addWidget(self.main_task_screen)    # 3
        self.stacked_widget.addWidget(self.assembly_screen)     # 4
        self.stacked_widget.addWidget(self.short_rest_screen)   # 5
        self.stacked_widget.addWidget(self.long_rest_screen)    # 6
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)
        
        self.quit_shortcut = QShortcut(QKeySequence("q"), self)
        self.quit_shortcut.activated.connect(QApplication.instance().quit)
        
        self.mistake_shortcut = QShortcut(QKeySequence("F12"), self)
        self.mistake_shortcut.activated.connect(self.trigger_mistake)
        
        # Puntos de recolección
        self.f13_shortcut = QShortcut(QKeySequence("F13"), self)
        self.f13_shortcut.activated.connect(lambda: self.assembly_screen.handover_received(1))

        self.f14_shortcut = QShortcut(QKeySequence("F14"), self)
        self.f14_shortcut.activated.connect(lambda: self.assembly_screen.handover_received(2))

        send_marker("Screen_Setup")
        
    def setup_finished_callback(self):
        self.scenarios = active_scenarios_list.copy()
        random.shuffle(self.scenarios)
        
        print("\n" + "="*50)
        print("ORDEN DE ESCENARIOS:")
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
        
        # 300 segundos = 5 minutos por escenario
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
                self.stacked_widget.setCurrentIndex(6)
                return
            elif self.pending_short_rest:
                self.pending_short_rest = False
                self.master_timer.stop()
                self.short_rest_screen.start_rest()
                self.stacked_widget.setCurrentIndex(5)
                return

        if difficulty != "hard" and self.current_trial >= self.max_trials:
            send_marker("Experiment_Complete_Trial_Limit")
            QApplication.instance().quit()
            return
            
        self.current_trial += 1
        send_marker(f"Screen_Trial_Cycle_{self.current_trial}_Start")

        self.retrieval_screen.start_retrieval()
        self.stacked_widget.setCurrentIndex(2)

    def show_math_task(self):
        send_marker(f"Screen_MathTask_Trial_{self.current_trial}")
        self.main_task_screen.start_challenge()
        self.stacked_widget.setCurrentIndex(3)

    def show_assembly_task(self):
        target_pt = 1 if (self.current_trial % 2 != 0) else 2

        # Extrae el patrón balanceado de 5 bloques de la secuencia asignada
        pattern_index = (self.current_trial - 1) % len(selected_sequence_patterns)
        pattern = selected_sequence_patterns[pattern_index]

        self.assembly_screen.start_assembly(target_pt, pattern)
        self.stacked_widget.setCurrentIndex(4)

    def on_handover_complete(self, point_pressed):
        global robot_process
        if robot_process is not None and robot_process.poll() is None:
            try:
                # Escribe '1\n' o '2\n' directamente a stdin de robot_sequence.py
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
    global robot_process
    send_marker("Application_Closing")
    
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
    init_lsl()
    start_haptic_thread()
    
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_resources)
    
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