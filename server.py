import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware
from driving_controller import DrivingController
import subprocess
from cv_settings import CvSettings, currentSettingsState, currentSettingsStateLock

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

drivingController = DrivingController()

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

@app.post("/change_direction")
def change_direction():
    global drivingController
    with drivingController.drivingStateLock:
        drivingController.drivingState.currentDrivingDirection = not drivingController.drivingState.currentDrivingDirection

@app.post("/reset_auto_mode")
def reset_auto_mode():
    global drivingController
    print("Resetting auto mode")
    drivingController.reset()

def get_temperature():
    try:
        result = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
        temp = result.stdout.split("=")[1].split("'")[0]
        return temp
    except Exception as e:
        return {"error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection established.")
    while True:
        try:
            # Wait for the driving controller to finish processing
            drivingController.finishedProcessing.clear()
            await asyncio.get_running_loop().run_in_executor(None, drivingController.finishedProcessing.wait)

            with drivingController.drivingStateLock:
                currentStage = drivingController.drivingState.currentStage.name
                overallDrivingDirection = "FORWARD" if drivingController.drivingState.overallDrivingDirection else "BACKWARD"
            with drivingController.outputStateLock:
                latestDriveCommand = drivingController.outputState.latestDriveCommand
                latestHoeCommand = drivingController.outputState.latestHoeCommand

                latestFrontCombinedImg = drivingController.outputState.frontCombinedImg
                latestRearCombinedImg = drivingController.outputState.rearCombinedImg

                frontLostContext = drivingController.outputState.frontLostContext
                rearLostContext = drivingController.outputState.rearLostContext
            with drivingController.serialLogHistoryLock:
                serialLogHistory = drivingController.serialLogHistory.copy()

            temperature = get_temperature()
            
            jsonData = {
                "frontImg": latestFrontCombinedImg,
                "rearImg": latestRearCombinedImg,
                "temperature": temperature,
                "serialLogHistory": serialLogHistory,
                "latestDriveCommand": latestDriveCommand,
                "latestHoeCommand": latestHoeCommand,
                "currentStage": currentStage,
                "overallDrivingDirection": overallDrivingDirection,
                "frontLostContext": frontLostContext,
                "rearLostContext": rearLostContext,
            }

            await websocket.send_json(jsonData)
        except Exception as e:
            # print(f"WebSocket error: {e}")
            break