"""Robot control: speed level over TCP and the robot_sequence.py subprocess."""

import socket
import subprocess
import sys
import threading

from config import DIFFICULTY_PORT, ROBOT_OWN_IP


_robot_process = None


def set_robot_speed(scenario_name):
    level = 1

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


def start_robot_process():
    global _robot_process
    if _robot_process is None or _robot_process.poll() is not None:
        try:
            _robot_process = subprocess.Popen(
                [sys.executable, "robot_sequence.py"],
                stdin=subprocess.PIPE,
                text=True
            )
        except Exception as e:
            print(f"Could not launch robot_sequence.py: {e}")


def send_point_to_robot(point_pressed: int):
    if _robot_process is not None and _robot_process.poll() is None:
        try:
            _robot_process.stdin.write(f"{point_pressed}\n")
            _robot_process.stdin.flush()
        except Exception:
            pass


def stop_robot_process():
    if _robot_process is not None:
        _robot_process.terminate()
