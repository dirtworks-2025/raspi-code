from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
import json
import cv2
from driptape_regression import annotate_frame, AnnotationSettings
import subprocess

app = FastAPI()

class AnnotationSettingsState:
    settings: AnnotationSettings
    path: str

    def update(self, newSettings: AnnotationSettings):
        self.settings = newSettings
        
        with open(self.path, "w") as f:
            json.dump(newSettings.dict(), f)
    
    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.settings.dict(), f)

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

# Mount the "static" folder for serving JS and other static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

@app.get("/")
def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

webcams = {
    "front": Webcam(2),
    "rear": Webcam(0, rotate=True),
}

def generate_frames(webcam: Webcam):
    fps = 10
    frame_interval = int(1000 / fps)  # Convert seconds to milliseconds for waitKey()

    while webcam.capture.isOpened():
        frame = webcam.get_frame()
        if frame is None:
            break

        frame = annotate_frame(frame, currentSettingsState.settings)

        _, buffer = cv2.imencode(".jpg", frame)  # Encode frame as JPEG
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

        cv2.waitKey(frame_interval)  # Ensures frame delay

@app.get("/video/{cam_id}")
def video_feed(cam_id: str):
    webcam = webcams[cam_id]
    return StreamingResponse(generate_frames(webcam), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/settings")
def get_settings():
    return currentSettingsState.settings.dict()

@app.post("/settings")
def set_settings(settings: AnnotationSettings):
    currentSettingsState.update(settings)

@app.get("/temperature")
def get_temperature():
    try:
        result = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
        temp = result.stdout.split("=")[1].split("'")[0]
        return {"temperature": temp}
    except Exception as e:
        return {"error": str(e)}