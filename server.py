from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
import json
import cv2
from driptape_regression import annotate_frame, AnnotationSettings

app = FastAPI()

class AnnotationSettingsState:
    settings: AnnotationSettings

    def update(self, newSettings: AnnotationSettings):
        self.settings = newSettings

    def __init__(self):
        self.settings = AnnotationSettings(minSat=0, maxSat=255)

currentSettingsState = AnnotationSettingsState()

# Mount the "static" folder for serving JS and other static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

@app.get("/")
def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

captures = {
    "front": cv2.VideoCapture(0),
    "rear": cv2.VideoCapture(2),
}

def generate_frames(cap: cv2.VideoCapture):
    fps = 10
    frame_interval = int(1000 / fps)  # Convert seconds to milliseconds for waitKey()

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        frame = annotate_frame(frame, currentSettingsState.settings)

        _, buffer = cv2.imencode(".jpg", frame)  # Encode frame as JPEG
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

        cv2.waitKey(frame_interval)  # Ensures frame delay

@app.get("/video/{cam_id}")
def video_feed(cam_id: str):
    cap = captures[cam_id]
    return StreamingResponse(generate_frames(cap), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/settings")
def set_settings(settings: AnnotationSettings):
    currentSettingsState.update(settings)