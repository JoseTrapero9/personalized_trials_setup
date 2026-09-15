# demo use case of the urscript port (30002) and the dashboard port (29999) used in simultaneous
# use this code for demos and showcasting system
# called in "test_use_case_1.py"

import socket
import time
import math

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
        # convert degrees to radians and send movej with two decimals
        radians_1 = [math.radians(deg) for deg in degrees_list_1]
        radians_2 = [math.radians(deg) for deg in degrees_list_2]
        cmd = f"movec([{radians_1[0]:.2f}, {radians_1[1]:.2f}, {radians_1[2]:.2f}, {radians_1[3]:.2f}, {radians_1[4]:.2f}, {radians_1[5]:.2f}], a={a}, v={v})\n"
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

    def move_left_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [128.61, -46.97, 68.62, -111.26, -89.09, -50.83] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_right_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [157.98, -79.92, 90.30, -100.16, -87.56, -22.26] 
        self._send_movej_degrees(degrees, delay=wait_time)

    def move_right_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [158.14, -70.42, 106.62, -126.15, -87.63, -21.80] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_disposal_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [22.80, -89.08, 103.10, -103.70, -89.89, -156.67] 
        self._send_movej_degrees(degrees, delay=wait_time)

    def move_disposal_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [22.86, -78.30, 117.68, -128.76, -90.17, -156.16] 
        self._send_movel_degrees(degrees, delay=wait_time)

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

def main():
    s = Scripter()
    d = Dashboard()
    
    try:
        s.open_gripper()
        s.close_gripper()
        s.open_gripper()

        # s.move_left_up(wait_time=8)
        s.move_home(wait_time=8)

        # s.move_left_down(wait_time=2)
        # s.close_gripper()
        # s.move_left_up(wait_time=4)
        
        # # s.move_home(wait_time=5.5)
        
        # s.move_disposal_down(wait_time=2)
        # s.move_disposal_up(wait_time=8)

    finally:
        # closing streams
        s.close()
        d.close()

if __name__ == "__main__":
    main()