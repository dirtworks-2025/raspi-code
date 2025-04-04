import time
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware
import json
import cv2
import asyncio
import threading
from frame_processor import process_frame, CvSettings, dont_process_frame
import subprocess
from serial_comms import ArduinoSerial
from typing import Literal

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

serialLogHistory = []
serialLogHistoryLock = threading.Lock()

def handle_serial_log(message: str):
    print(message)
    # Append the message to the serial log history
    with serialLogHistoryLock:
        serialLogHistory.append(message)
        if len(serialLogHistory) > 100:
            serialLogHistory.pop(0)

arduinoSerial = ArduinoSerial(handle_serial_log)

DrivingDirectionType = Literal["FORWARD", "BACKWARD"]
drivingDirection = "FORWARD"  # Default driving direction
drivingDirectionLock = threading.Lock()

fps = 30  # Frames per second for the video stream

class AnnotationSettingsState:
    settings: CvSettings
    path: str

    def update(self, newSettings: CvSettings):
        self.settings = newSettings
        self.save()
    
    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.settings.dict(), f, indent=4)

    def load(self):
        try:
            with open(self.path, "r") as f:
                self.settings = CvSettings(**json.load(f))
        except:
            raise ValueError("Failed to load settings from file.")

    def __init__(self, path: str):
        self.path = path
        self.load()

currentSettingsState = AnnotationSettingsState("state/settings.json")
currentSettingsStateLock = threading.Lock()

class Webcam:
    def __init__(self, id: int, rotate: bool = False):
        self.capture = cv2.VideoCapture(id)
        self.rotate = rotate

    def get_frame(self):
        success, frame = self.capture.read()
        if not success:
            return None
        if self.rotate:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        return frame

    def get_rotated_frame(self):
        frame = self.get_frame()
        if frame is not None:
            return cv2.rotate(frame, cv2.ROTATE_180)
        return None

class Webcams:
    def __init__(self):
        self.front = Webcam(2)
        self.rear = Webcam(0, rotate=True)

    def get_front_frame(self, swapped: bool = False):
        if swapped:
            return self.rear.get_rotated_frame()
        return self.front.get_frame()
    
    def get_rear_frame(self, swapped: bool = False):
        if swapped:
            return self.front.get_rotated_frame()
        return self.rear.get_frame()

latestFrontFrameOutput = None
latestFrontFrameOutputLock = threading.Lock()
latestRearFrameOutput = None
latestRearFrameOutputLock = threading.Lock()

def frame_processor():
    global latestFrontFrameOutput, latestFrontFrameOutputLock, \
           latestRearFrameOutput, latestRearFrameOutputLock, \
           currentSettingsState, currentSettingsStateLock, \
           fps
    webcams = Webcams()
    while True:
        with currentSettingsStateLock:
            settings = currentSettingsState.settings
        with drivingDirectionLock:
            direction = drivingDirection
        maybeSwapped = settings.swapCameras
        frontFrame = webcams.get_front_frame(maybeSwapped)
        rearFrame = webcams.get_rear_frame(maybeSwapped)

        # Only process either front or rear frame depending on driving direction
        frontFrameOutput = None
        if frontFrame is not None and direction == "FORWARD":
            frontFrameOutput = process_frame(frontFrame, settings, isRearCamera=False)
            maybeSendSerialCmds(
                frontFrameOutput.hoeCmd, frontFrameOutput.driveCmd, frontFrameOutput.lostContext
            )
        elif frontFrame is not None and direction == "BACKWARD":
            frontFrameOutput = dont_process_frame(frontFrame)

        rearFrameOutput = None
        if rearFrame is not None and direction == "BACKWARD":
            rearFrameOutput = process_frame(rearFrame, settings, isRearCamera=True)
            maybeSendSerialCmds(
                rearFrameOutput.hoeCmd, rearFrameOutput.driveCmd, rearFrameOutput.lostContext
            )
        elif rearFrame is not None and direction == "FORWARD":
            rearFrameOutput = dont_process_frame(rearFrame)

        with latestFrontFrameOutputLock:
            latestFrontFrameOutput = frontFrameOutput
        with latestRearFrameOutputLock:
            latestRearFrameOutput = rearFrameOutput
        time.sleep(1 / fps)

def maybeSendSerialCmds(hoeCmd: str, driveCmd: str, lostContext: bool):
    if lostContext:
        arduinoSerial.send_command("hoe 0 0")
        arduinoSerial.send_command("drive 0 0")
        return
    if hoeCmd:
        arduinoSerial.send_command(hoeCmd)
    # if driveCmd:
    #     arduinoSerial.send_command(driveCmd)

# Mount the "static" folder for serving JS and other static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

@app.get("/")
def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/settings")
def get_settings():
    with currentSettingsStateLock:
        settings = currentSettingsState.settings
    return settings.dict()

@app.post("/settings")
def set_settings(settings: CvSettings):
    with currentSettingsStateLock:
        currentSettingsState.update(settings)

def get_temperature():
    try:
        result = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
        temp = result.stdout.split("=")[1].split("'")[0]
        return temp
    except Exception as e:
        return {"error": str(e)}

@app.on_event("startup")
def start_background_tasks():
    threading.Thread(target=frame_processor, daemon=True).start()
    print("Background frame processor started.")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            with latestFrontFrameOutputLock:
                frontFrameOutput = latestFrontFrameOutput
            with latestRearFrameOutputLock:
                rearFrameOutput = latestRearFrameOutput
            temperature = get_temperature()
            with serialLogHistoryLock:
                serialLog = serialLogHistory.copy()

            jsonData = {
                "front": frontFrameOutput.dict() if frontFrameOutput else None,
                "rear": rearFrameOutput.dict() if rearFrameOutput else None,
                "temperature": temperature,
                "serialLogHistory": serialLog,
            }

            await websocket.send_json(jsonData)

            await asyncio.sleep(1 / fps)
        except Exception as e:
            print(f"WebSocket error: {e}")
            break