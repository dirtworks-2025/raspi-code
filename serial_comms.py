import serial
import threading
import time
import glob
from typing import Callable


def find_acm_port():
    ports = glob.glob('/dev/ttyACM*')
    if ports:
        return ports[0]
    else:
        print("No ACM port found.")
    return None

class ArduinoSerial:
    def __init__(self, log: Callable[[str], None], port=None, baudrate=115200):
        self.port = port if port else find_acm_port()
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.thread = None
        self.log = log

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Allow time for Arduino reset
            self.ser.flushInput()
            self.ser.flushOutput()
            self.running = True
            
            self.thread = threading.Thread(target=self._read_from_port, daemon=True)
            self.thread.start()
            self.log(f"[Arduino] Connected to {self.port} at {self.baudrate} baud")
        except serial.SerialException as e:
            self.log(f"Serial initialization error: {e}")
    
    def _read_from_port(self):
        while self.running:
            try:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        self.log(f"[Arduino] {line}")
            except Exception as e:
                self.log(f"[Read Error] {e}")
                break

    def send_command(self, cmd):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(cmd.encode('utf-8') + b'\n')
                self.log(f"[Send] {cmd.strip()}")
            except serial.SerialException as e:
                self.log(f"[Write Error] {e}")

    def close(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.log("[Connection closed]")