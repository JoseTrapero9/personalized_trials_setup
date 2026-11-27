"""Robot (UR) handover sequence, driven by the GUI (robot.py starts it and writes commands to its stdin).

Commands, one per line:
    go 1 / go 2   move above collection point 1 (left) / 2 (right) and wait there
    1 / 2         the participant pressed that point's button: pick the piece up there, bring it to the
                  disposal, bring an empty piece back (same moves and timings as before)
    home          park at the home position (end of a condition / training block)
    quit          home and end

The GUI decides the point of every round (round 1 of every condition and of every training block = point 1),
so the robot can never get out of step with the screen (before, the robot just alternated left/right for
the whole program run: a 5-round training block made the next block start on the wrong side, and after
20 handovers the sequence ended in the middle of a condition). Commands that arrive while the robot is
still moving wait until the current move sequence is finished, so a move is never cut off.
"""

import socket
import time
import math
import sys

HOST = "192.168.29.61"
PORT_SCRIPT = 30002
PORT_DASHBOARD = 29999

class Scripter:
    def __init__(self):
        # connect to robot script controller
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT_SCRIPT))

    def send_command(self, cmd: str, delay: float = 0.00):
        # send a urscript command and optionally wait
        self.sock.sendall(cmd.encode('utf-8'))
        if delay:
            time.sleep(delay)

    def _send_movej_degrees(self, degrees_list, a=0.90, v=0.90, delay=2.50):
        # convert degrees to radians and send movej with two decimals
        radians = [math.radians(deg) for deg in degrees_list]
        cmd = f"movej([{radians[0]:.2f}, {radians[1]:.2f}, {radians[2]:.2f}, {radians[3]:.2f}, {radians[4]:.2f}, {radians[5]:.2f}], a={a}, v={v})\n"
        self.send_command(cmd, delay)

    def _send_movel_degrees(self, degrees_list, a=1.50, v=1.00, delay=2.50):
        # convert degrees to radians and send movel with two decimals
        radians = [math.radians(deg) for deg in degrees_list]
        cmd = f"movel([{radians[0]:.2f}, {radians[1]:.2f}, {radians[2]:.2f}, {radians[3]:.2f}, {radians[4]:.2f}, {radians[5]:.2f}], a={a}, v={v})\n"
        self.send_command(cmd, delay)

    def _send_movec_degrees(self, degrees_list_1, degrees_list_2, a=0.90, v=0.90, delay=2.50):
        # convert degrees to radians
        radians_1 = [math.radians(deg) for deg in degrees_list_1]
        radians_2 = [math.radians(deg) for deg in degrees_list_2]
        
        # format joint vectors with two decimal places
        wp1_str = ", ".join(f"{r:.2f}" for r in radians_1)
        wp2_str = ", ".join(f"{r:.2f}" for r in radians_2)
        
        cmd = f"movec([{wp1_str}], [{wp2_str}], a={a}, v={v})\n"
        self.send_command(cmd, delay)

    def open_gripper(self):
        # set digital output 0 to False
        self.send_command("set_tool_digital_out(0, False)\n", 0.5)
        # set digital output 1 to True
        self.send_command("set_tool_digital_out(1, True)\n", 0.6)
        # set digital output 1 to False
        self.send_command("set_tool_digital_out(1, False)\n", 0.5)

    def close_gripper(self):
        # set digital output 0 to True
        self.send_command("set_tool_digital_out(0, True)\n", 0.5)

    # Home position
    def move_home(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [112.76, -103.21, 114.67, -100.47, -86.53, -63.79] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    # Collection movements
    def move_left_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [128.66, -50.45, 39.38, -77.93, -87.86, -51.88] 
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_left_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [128.66, -50.45, 39.38, -77.93, -87.86, -51.88] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_left_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [128.61, -46.97, 68.62, -111.26, -89.09, -50.83] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_right_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [157.98, -79.92, 90.30, -100.16, -87.56, -22.26] 
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_right_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [157.98, -79.92, 90.30, -100.16, -87.56, -22.26] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_right_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [158.14, -70.42, 106.62, -126.15, -87.63, -21.80] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_disposal_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [182.07, -96.25, 100.1, -96.48, -88.76, 97.41] 
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_disposal_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [182.07, -96.25, 100.1, -96.48, -88.76, 97.41]
        self._send_movel_degrees(degrees, delay=wait_time, a=0.5)

    def move_disposal_down(self, wait_time: float = 2.00,):
        # define your down position in degrees
        degrees = [182.03, -92.55, 114.27, -114.36, -88.87, 97.62] 
        self._send_movel_degrees(degrees, delay=wait_time, a=0.5)

    def move_return_empty_piece_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [129.49, -78.89, 119.51, -129.43, -87.66, -51.00] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_return_empty_piece_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [129.6,-88.67 ,108.05 ,-108.22 ,-87.68 ,-51.06] 
        self._send_movej_degrees(degrees, delay=wait_time)

    def move_pickup_empty_piece_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [188.54, -58.50, 89.90, -124.05, -89.30, 104.27]  
        self._send_movel_degrees(degrees, delay=wait_time, a=0.5)

    def move_pickup_empty_piece_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [188.60, -67.31, 68.36, -93.71, -89.09, 103.92] 
        self._send_movej_degrees(degrees, delay=wait_time)

    def move_return_midpoint(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [129.6,-88.67 ,108.05 ,-108.22 ,-87.68 ,-51.06]
        self._send_movej_degrees(degrees, delay=wait_time)

    def close(self):
        # clean up script socket
        self.sock.close()

class Dashboard:
    def __init__(self):
        # connect to dashboard server
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT_DASHBOARD))
        # clear the welcome buffer
        self.sock.recv(1024)

    def send_command(self, command: str):
        # send dashboard command and print response
        self.sock.sendall((command + "\n").encode('utf-8'))
        response = self.sock.recv(1024).decode('utf-8')
        print(f"dashboard sent: {command}  -->  received: {response.strip()}")

    def close(self):
        # clean up dashboard socket
        self.sock.close()

def deliver_and_return_empty(s):
    """After a pick-up: piece to the disposal, empty piece back (identical for both points)."""
    s.move_home(wait_time=2.9 if s.last_point == 1 else 2.5)
    s.move_disposal_up(wait_time=4.5)
    s.move_disposal_down(wait_time=1.1)
    s.open_gripper()
    s.movel_disposal_up(wait_time=1.5)
    s.move_pickup_empty_piece_up(wait_time=2.5)
    s.move_pickup_empty_piece_down(wait_time=2.4)
    s.close_gripper()
    s.move_pickup_empty_piece_up(wait_time=2.5)
    s.move_return_empty_piece_up(wait_time=4.2)
    s.move_return_empty_piece_down(wait_time=1)
    s.open_gripper()
    s.move_return_empty_piece_up(wait_time=1.5)


def go_to_point(s, point, where):
    """Move above collection point 1 / 2. where = position the robot is at now."""
    if where == point:
        return
    if where in (1, 2):                       # above the OTHER point: via home, never straight across
        s.move_home(wait_time=3.0)
        where = "home"
    if point == 1:
        s.move_left_up(wait_time=3)           # same as the old sequence
    else:
        s.move_right_up(wait_time=1.9 if where == "return" else 3.0)


def pick_up(s, point):
    s.last_point = point
    if point == 1:
        s.move_left_down(wait_time=1.9)
        s.close_gripper()
        s.movel_left_up(wait_time=1.9)
    else:
        s.move_right_down(wait_time=1.3)
        s.close_gripper()
        s.movel_right_up(wait_time=1.7)


def main():
    s = Scripter()
    d = Dashboard()
    s.last_point = 1
    where = "home"                            # home | 1 | 2 | return (above the empty-piece place)
    try:
        s.open_gripper()
        s.close_gripper()
        s.open_gripper()
        s.move_home(wait_time=5)
        print("[ROBOT] ready, waiting for the GUI", flush=True)
        for line in sys.stdin:                # blocks until the GUI writes a command
            cmd = line.strip().lower()
            if not cmd:
                continue
            print(f"[ROBOT] command: {cmd}", flush=True)
            if cmd in ("go 1", "go 2"):
                point = int(cmd[-1])
                go_to_point(s, point, where)
                where = point
            elif cmd in ("1", "2"):
                point = int(cmd)
                go_to_point(s, point, where)  # normally already there
                pick_up(s, point)
                deliver_and_return_empty(s)
                where = "return"
            elif cmd == "home":
                if where != "home":
                    s.move_home(wait_time=3.0)
                where = "home"
            elif cmd == "quit":
                break
            else:
                print(f"[ROBOT] unknown command ignored: {cmd}", flush=True)
        s.move_home(wait_time=8)
    finally:
        s.close()
        d.close()


if __name__ == "__main__":
    main()
