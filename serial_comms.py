import serial
import threading
import time

class ArduinoSerial:
    def __init__(self, port="/dev/ttyACM0", baudrate=115200, log=True):
        self.port = port
        self.baudrate = baudrate
        self.log = log
        self.ser = None
        self.running = False
        self.thread = None

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Allow time for Arduino reset
            self.ser.flushInput()
            self.ser.flushOutput()
            self.running = True

            if self.log:
                self.thread = threading.Thread(target=self._read_from_port, daemon=True)
                self.thread.start()
        except serial.SerialException as e:
            print(f"Serial initialization error: {e}")
    
    def _read_from_port(self):
        while self.running:
            try:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        print(f"[Arduino] {line}")
            except Exception as e:
                print(f"[Read Error] {e}")
                break

    def send_command(self, cmd):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(cmd.encode('utf-8'))
                if self.log:
                    print(f"[Send] {cmd.strip()}")
            except serial.SerialException as e:
                print(f"[Write Error] {e}")

    def close(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[Connection closed]")

# Example usage:
# arduino = ArduinoSerial()
# arduino.send_command("LED_ON\n")
# time.sleep(5)
# arduino.close()
