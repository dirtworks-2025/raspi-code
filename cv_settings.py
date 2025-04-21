import json
import threading
from pydantic import BaseModel


class CvSettings(BaseModel):
    minHue: int
    maxHue: int
    minSaturation: int
    maxSaturation: int
    minValue: int
    maxValue: int
    closeKernel: int
    openKernel: int
    distThreshold: int
    verticalDilationIterations: int
    r2Threshold: int
    # swapCameras: bool

class CvSettingsState:
    settings: CvSettings
    path: str

    def update(self, newSettings: CvSettings):
        self.settings = newSettings
        # self.save()
    
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

currentSettingsState = CvSettingsState("state/settings.json")
currentSettingsStateLock = threading.Lock()