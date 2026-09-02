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

    def movej_up_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [133.74, -69.16, 65.49, -86.00, -89.11, -47.40]  
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_up_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [133.74, -69.16, 65.49, -86.00, -89.11, -47.40]  
        self._send_movel_degrees(degrees, delay=wait_time)

    def move_down_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [133.67, -60.54, 92.05, -121.19, -89.31, -46.98] 
        self._send_movel_degrees(degrees, delay=wait_time) 
       
    def move_home(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [145.63, -95.27, 95.41, -88.83, -89.03, -35.92] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    def move_ramp_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [123.85, -41.43, 27.76, -76.01, -89.21, -57.42] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    def move_ramp_2(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [189.35, -90.94, 113.05, -111.83, -89.39, -85.19] 
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

def main():
    s = Scripter()
    d = Dashboard()
    
    try:
        s.move_home(wait_time=8)

    finally:
        # closing streams
        s.close()
        d.close()

if __name__ == "__main__":
    main()