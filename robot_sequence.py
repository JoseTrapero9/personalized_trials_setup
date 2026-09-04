import socket
import time
import math
import sys
###test
HOST = "192.168.29.61"
PORT_SCRIPT = 30002
PORT_DASHBOARD = 29999

def wait_for_gui_signal():
    # blocks execution until a line is written to standard input by the main application
    sys.stdin.readline()

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


    def move_down_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [90.18, -106.50, 146.41, -126.55, -91.51, -90.40]   
        self._send_movel_degrees(degrees, delay=wait_time)

    def movej_up_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [90.33, -120.05, 120.56, -87.16, -91.26, -90.78]   
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_up_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [90.33, -120.05, 120.56, -87.16, -91.26, -90.78]    
        self._send_movel_degrees(degrees, delay=wait_time)


    def move_down_collect_pt_2(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [114.18, -95, 138.4, -129.46, -90, -66.4] 
        self._send_movel_degrees(degrees, delay=wait_time) 

    def movel_up_collect_pt_2(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [114.28, -108.98, 119.48, -96.55, -89.75, -66.73]  
        self._send_movel_degrees(degrees, delay=wait_time)

    def movej_up_collect_pt_2(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [114.28, -108.98, 119.48, -96.55, -89.75, -66.73]     
        self._send_movej_degrees(degrees, delay=wait_time)


    def move_down_collect_pt_3(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [128.75, -83.96, 126.75, -128.84, -89.01, -51.85] 
        self._send_movel_degrees(degrees, delay=wait_time)  

    def movej_up_collect_pt_3(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [128.83, -97.30, 107.55, -96.28, -88.75, -52.20]  
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_up_collect_pt_3(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [128.83, -97.30, 107.55, -96.28, -88.75, -52.20]    
        self._send_movel_degrees(degrees, delay=wait_time)
       
    # Home position
    def move_home(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [143.85, -106.87, 116.87, -96.27, -87.73, -35.21] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    # Ramp movements
    def move_(self, wait_time: float = 2.00):
            # define your down position in degrees
            degrees = [143.85, -106.87, 116.87, -96.27, -87.73, -35.21] 
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
        # set the robot to go to the specific position and wait 15 seconds
        s.open_gripper()
        s.close_gripper()
        s.open_gripper()

        for i in range(3):  # repeat the sequence 3 times
            s.move_home(wait_time=5)

            # Going to first collection point
            s.movej_up_collect_pt_1(wait_time=3)
            s.move_down_collect_pt_1(wait_time=3)
            s.close_gripper()
            s.movel_up_collect_pt_1(wait_time=2.5)

            s.move_ramp_1_up(wait_time=4)
            s.move_ramp_1_down(wait_time=2)
            s.open_gripper()
            # skip the wait signal on the very first loop iteration
            if i > 0:
                wait_for_gui_signal()
            s.move_ramp_1_up(wait_time=1.5)

            # Going to second collection point
            s.movej_up_collect_pt_2(wait_time=2)
            s.move_down_collect_pt_2(wait_time=3)
            s.close_gripper()
            s.movel_up_collect_pt_2(wait_time=2.5)

            s.move_ramp_2_up(wait_time=4)
            s.move_ramp_2_down(wait_time=2)
            wait_for_gui_signal()
            s.open_gripper()
            s.move_ramp_2_up(wait_time=2)

            # Going to third collection point
            s.movej_up_collect_pt_3(wait_time=4)
            s.move_down_collect_pt_3(wait_time=3)
            s.close_gripper()
            s.movel_up_collect_pt_3(wait_time=2.5)

            s.move_ramp_1_up(wait_time=4)
            s.move_ramp_1_down(wait_time=2)
            wait_for_gui_signal()
            s.open_gripper()
            s.move_ramp_1_up(wait_time=1.5)

            # Going to fourth collection point
            s.movej_up_collect_pt_4(wait_time=3)
            s.move_down_collect_pt_4(wait_time=3)
            s.close_gripper()
            s.movel_up_collect_pt_4(wait_time=2.5)

            s.move_ramp_2_up(wait_time=4)
            s.move_ramp_2_down(wait_time=2)
            wait_for_gui_signal()
            s.open_gripper()
            s.move_ramp_2_up(wait_time=2)

        # End of cycle  
        s.move_home(wait_time=8)

    finally:
        # closing streams
        s.close()
        d.close()

if __name__ == "__main__":
    main()