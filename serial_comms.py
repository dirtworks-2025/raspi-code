import serial
import time

def main():
    port = "/dev/ttyACM0"  # Change this to match your Arduino's port (e.g., "/dev/ttyUSB0" on Linux/Mac)
    baudrate = 9600  # Adjust if needed to match the Arduino's serial settings

    sequence = [0, 5, 10, 15, 20, 25, 30, 25, 20, 15, 10, 5, 0, -5, -10, -15, -20, -25, -30, -25, -20, -15, -10, -5, 0]
    
    try:
        with serial.Serial(port, baudrate, timeout=1) as ser:
            time.sleep(2)  # Allow time for Arduino to reset
            while True:
                for value in sequence:
                    ser.write(f"{value}\n".encode())  # Send value as a string
                    print(f"Sent: {value}")
                    time.sleep(5)
    except serial.SerialException as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("Serial communication stopped.")

if __name__ == "__main__":
    main()
