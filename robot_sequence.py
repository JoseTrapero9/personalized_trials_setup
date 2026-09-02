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
        degrees = [140.74, -69.39, 107.61, -126.45, -89.21, -40.37]  
        self._send_movel_degrees(degrees, delay=wait_time)

    def movej_up_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [140.80, -80.52, 89.73, -97.43, -88.99, -40.69]  
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_up_collect_pt_1(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [140.80, -80.52, 89.73, -97.43, -88.99, -40.69]   
        self._send_movel_degrees(degrees, delay=wait_time)


    def move_down_collect_pt_2(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [131.92, -60.79, 94.15, -121.57, -89.45, -49.23] 
        self._send_movel_degrees(degrees, delay=wait_time) 

    def movel_up_collect_pt_2(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [131.97, -70.25, 75.21, -93.17, -89.26, -49.56]  
        self._send_movel_degrees(degrees, delay=wait_time)

    def movej_up_collect_pt_2(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [131.97, -70.25, 75.21, -93.17, -89.26, -49.56]    
        self._send_movej_degrees(degrees, delay=wait_time)


    def move_down_collect_pt_3(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [121.42, -71.46, 111.02, -127.81, -89.81, -59.67] 
        self._send_movel_degrees(degrees, delay=wait_time)  

    def movej_up_collect_pt_3(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [121.48, -83.08, 93.52, -98.70, -89.59, -59.99]  
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_up_collect_pt_3(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [121.48, -83.08, 93.52, -98.70, -89.59, -59.99]  
        self._send_movel_degrees(degrees, delay=wait_time)


    def move_down_collect_pt_4(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [129.86, -81.80, 125.36, -131.78, -89.59, -51.20] 
        self._send_movel_degrees(degrees, delay=wait_time)

    def movej_up_collect_pt_4(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [129.93, -95.39, 106.98, -99.80, -89.33, -51.53]  
        self._send_movej_degrees(degrees, delay=wait_time)

    def movel_up_collect_pt_4(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [129.93, -95.39, 106.98, -99.80, -89.33, -51.53]  
        self._send_movel_degrees(degrees, delay=wait_time)
       
    # Home position
    def move_home(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [145.63, -95.27, 95.41, -88.83, -89.03, -35.92] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    # Ramp movements
    def move_ramp_1_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [130.98, -45.40, 31.55, -77.25, -88.15, -54.98] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    def move_ramp_1_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [130.94, -47.09, 52.65, -96.66, -88.17, -54.73] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    def move_ramp_2_up(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [184.48, -75.16, 67.15, -83.44, -89.57, 4.23] 
        self._send_movej_degrees(degrees, delay=wait_time) 

    def move_ramp_2_down(self, wait_time: float = 2.00):
        # define your down position in degrees
        degrees = [184.42, -72.68, 91.43, -110.18, -89.67, 4.55] 
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