from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
import json
import cv2

app = FastAPI()

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
    while True:
        success, frame = cap.read()
        if not success:
            break

        frame = cv2.resize(frame, (360, 240))
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        _, buffer = cv2.imencode(".jpg", frame)  # Encode frame as JPEG
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

@app.get("/video/{cam_id}")
def video_feed(cam_id: str):
    cap = captures[cam_id]
    return StreamingResponse(generate_frames(cap), media_type="multipart/x-mixed-replace; boundary=frame")
