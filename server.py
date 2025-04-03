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
from frame_processor import process_frame, AnnotationSettings
import subprocess
from serial_comms import ArduinoSerial

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

arduinoSerial = ArduinoSerial()

fps = 5  # Frames per second for the video stream

class AnnotationSettingsState:
    settings: AnnotationSettings
    path: str

    def update(self, newSettings: AnnotationSettings):
        self.settings = newSettings
        self.save()
    
    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.settings.dict(), f, indent=4)

    def load(self):
        try:
            with open(self.path, "r") as f:
                self.settings = AnnotationSettings(**json.load(f))
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
        maybeSwapped = settings.swapCameras
        frontFrame = webcams.get_front_frame(maybeSwapped)
        rearFrame = webcams.get_rear_frame(maybeSwapped)
        frontFrameOutput = process_frame(frontFrame, settings, isRearCamera=False) if frontFrame is not None else None
        rearFrameOutput = process_frame(rearFrame, settings, isRearCamera=True) if rearFrame is not None else None

        if frontFrameOutput is not None:
            maybeSendSerialCmds(
                frontFrameOutput.hoeCmd, frontFrameOutput.driveCmd, frontFrameOutput.lostContext
            )
        # if rearFrameOutput is not None:
        #     maybeSendSerialCmds(
        #         rearFrameOutput.hoeCmd, rearFrameOutput.driveCmd, rearFrameOutput.lostContext
        #     )

        with latestFrontFrameOutputLock:
            latestFrontFrameOutput = frontFrameOutput
        with latestRearFrameOutputLock:
            latestRearFrameOutput = rearFrameOutput
        time.sleep(1 / fps)

def maybeSendSerialCmds(hoeCmd: str, driveCmd: str, lostContext: bool):
    if lostContext:
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
def set_settings(settings: AnnotationSettings):
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

            jsonData = {
                "front": frontFrameOutput.dict() if frontFrameOutput else None,
                "rear": rearFrameOutput.dict() if rearFrameOutput else None,
                "temperature": temperature,
            }

            await websocket.send_json(jsonData)

            await asyncio.sleep(1 / fps)
        except Exception as e:
            print(f"WebSocket error: {e}")
            break