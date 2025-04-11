from enum import IntEnum
import threading
import time
from frame_processor import CvOutputLines, CvOutputs, Line, dont_process_frame, process_frame
from serial_comms import ArduinoSerial
from webcams import Webcams
from cv_settings import currentSettingsState, currentSettingsStateLock

CONTEXT_TIMEOUT_SECONDS = 1.0
DRIVE_BLIND_SECONDS = 2.0
HOE_UP_SECONDS = 2.0
HOE_DOWN_SECONDS = 2.0
STD_CMD_DELAY_SECONDS = 0.1

DRIVING_SPEED = 0.1 # This is the speed at which the robot will drive, between 0 and 1

class DrivingDirection:
    FORWARD = True
    BACKWARD = False

class CameraDirection:
    FRONT = True
    REAR = False

class RcControlMode(IntEnum):
    AUTO = 0
    MANUAL = 1
    STOP = 2

class DrivingStage(IntEnum):
    CENTERING_HOE =            0
    STOP_CENTERING_HOE =       1
    LOWERING_HOE =             2
    DRIVING_NORMAL =           3
    DRIVING_BLIND =            4
    STOP_DRIVING =             5
    RAISING_HOE =              6
    FINISHED_ROW =             7

    @classmethod
    def next(cls, current):
        members = list(cls)
        index = members.index(current)
        newIndex = (index + 1) % len(members)
        return members[newIndex]
    
    @classmethod
    def nextWithoutHoe(cls, current):
        excludedStages = [
            cls.LOWERING_HOE,
            cls.RAISING_HOE,
        ]
        members = list(cls)
        members = [member for member in members if member not in excludedStages]
        index = members.index(current)
        newIndex = (index + 1) % len(members)
        return members[newIndex]

class DrivingState:
    def __init__(self):
        self.rcControlMode = RcControlMode.MANUAL
        self.drivingDirection = DrivingDirection.FORWARD
        self.currentStage = DrivingStage.CENTERING_HOE
        self.lastStageChange = 0
        self.lastHadContext = 0
        self.useHoe = True

class OutputState:
    def __init__(self):
        self.latestDriveCommand = None
        self.latestGantryCommand = None

        self.frontCombinedImg = None
        self.rearCombinedImg = None

        self.frontLostContext = False
        self.rearLostContext = False
    
class DrivingController:
    def __init__(self):
        self.readyForWebsocket = threading.Event()

        self.drivingState = DrivingState()
        self.drivingStateLock = threading.Lock()
        self.outputState = OutputState()
        self.outputStateLock = threading.Lock()

        self.serialLogHistory = []
        self.serialLogHistoryLock = threading.Lock()
        self.arduinoSerial = ArduinoSerial(self.handleArduinoSerialLog)

        threading.Thread(target=self.controllerLoop, daemon=True).start()

    def reset(self):
        with self.drivingStateLock:
            useHoe = self.drivingState.useHoe
            self.drivingState = DrivingState()
            self.drivingState.useHoe = useHoe
        with self.outputStateLock:
            self.outputState = OutputState()
        print("Reset driving controller state")

    def startAutoMode(self, serialMsg: str):
        if "FORWARD" in serialMsg:
            self.drivingState.drivingDirection = DrivingDirection.FORWARD
            print("Setting direction to FORWARD")
        elif "BACKWARD" in serialMsg:
            self.drivingState.drivingDirection = DrivingDirection.BACKWARD
            print("Setting direction to BACKWARD")
        with self.drivingStateLock:
            self.drivingState.rcControlMode = RcControlMode.AUTO
            print("Starting auto mode")

    def advanceStage(self):
        with self.drivingStateLock:
            if self.drivingState.useHoe:
                self.drivingState.currentStage = DrivingStage.next(self.drivingState.currentStage)
            else:
                self.drivingState.currentStage = DrivingStage.nextWithoutHoe(self.drivingState.currentStage)
            
            print(f"Advancing to stage {self.drivingState.currentStage.name}")
            self.drivingState.lastStageChange = time.time()

    def handleArduinoSerialLog(self, message: str):
        print(message)

        # Only start the controller loop if the robot is in auto mode
        if "mode 0" in message:
            self.startAutoMode(message) # pass message along to set the direction
        elif "mode 1" in message:
            self.reset()
            self.drivingState.rcControlMode = RcControlMode.MANUAL
        elif "mode 2" in message:
            self.reset()
            self.drivingState.rcControlMode = RcControlMode.STOP

        with self.serialLogHistoryLock:
            self.serialLogHistory.append(message)
            if len(self.serialLogHistory) > 100:
                self.serialLogHistory.pop(0)

    def raiseHoe(self):
        self.arduinoSerial.send_command("hoe home")
        time.sleep(HOE_UP_SECONDS)
    
    def lowerHoe(self):
        self.arduinoSerial.send_command("hoe 0")
        time.sleep(HOE_DOWN_SECONDS)

    def sendDriveCommand(self, driveCmd: str):
        if driveCmd is None:
            return
        self.arduinoSerial.send_command(driveCmd)

    def controllerLoop(self):
        webcams = Webcams()
        while True:
            # Get a snapshot of the current settings and the current state of the controller
            with currentSettingsStateLock:
                settings = currentSettingsState.settings
            with self.drivingStateLock:
                drivingState = self.drivingState

            # Get the current frames from the webcams
            maybeSwapped = settings.swapCameras
            frontFrame = webcams.get_front_frame(maybeSwapped)
            rearFrame = webcams.get_rear_frame(maybeSwapped)

            # Determine which camera to process based on the current stage and driving direction
            cameraToProcess = drivingState.drivingDirection

            # Process the frames to get the lines, combined images, and drive commands
            driveCmd: str = None
            gantryCmd: str = None
            lostContext: bool = False
            frontFrameOutput: CvOutputs = None
            rearFrameOutput: CvOutputs = None
            
            if frontFrame is not None and cameraToProcess == CameraDirection.FRONT:
                frontFrameOutput = process_frame(frontFrame, settings)
                lostContext = frontFrameOutput.lostContext
                driveCmd = getDriveCmd(
                    cvOutputLines=frontFrameOutput.outputLines,
                    drivingState=drivingState,
                )
                gantryCmd = get_gantry_cmd(
                    cvOutputLines=frontFrameOutput.outputLines,
                    drivingState=drivingState,
                )
            elif frontFrame is not None and cameraToProcess == CameraDirection.REAR:
                frontFrameOutput = dont_process_frame(frontFrame)
            
            if rearFrame is not None and cameraToProcess == CameraDirection.REAR:
                rearFrameOutput = process_frame(rearFrame, settings)
                lostContext = rearFrameOutput.lostContext
                driveCmd = getDriveCmd(
                    cvOutputLines=rearFrameOutput.outputLines,
                    drivingState=drivingState,
                )
                gantryCmd = get_gantry_cmd(
                    cvOutputLines=rearFrameOutput.outputLines,
                    drivingState=drivingState,
                )
            elif rearFrame is not None and cameraToProcess == CameraDirection.FRONT:
                rearFrameOutput = dont_process_frame(rearFrame)

            if not lostContext:
                with self.drivingStateLock:
                    self.drivingState.lastHadContext = time.time()

            # Update the output state with the processed frames and drive command
            with self.outputStateLock:
                # If the drive command is None, use the last known command
                if driveCmd is not None:
                    self.outputState.latestDriveCommand = driveCmd
                else:
                    driveCmd = self.outputState.latestDriveCommand

                self.outputState.latestGantryCommand = gantryCmd
                self.outputState.frontCombinedImg = frontFrameOutput.combinedJpgTxt if frontFrameOutput else None
                self.outputState.rearCombinedImg = rearFrameOutput.combinedJpgTxt if rearFrameOutput else None

            # Update websocket with the latest images and commands
            self.readyForWebsocket.set()

            # Do nothing if the robot is not in auto mode
            if drivingState.rcControlMode != RcControlMode.AUTO:
                time.sleep(0.1)
                continue

            # Do nothing if the robot is in the finished row stage
            if drivingState.currentStage == DrivingStage.FINISHED_ROW:
                time.sleep(0.1)
                continue

            # Check if the robot is lost based on the time since it last had context
            # and the time since the last stage change
            with self.drivingStateLock:
                timeSinceLastContext = time.time() - drivingState.lastHadContext
                keepDrivingNormal = timeSinceLastContext < CONTEXT_TIMEOUT_SECONDS
                timeSinceStageChange = time.time() - self.drivingState.lastStageChange
                keepDrivingBlind = timeSinceStageChange < DRIVE_BLIND_SECONDS

            print(timeSinceStageChange, keepDrivingBlind)

            # Handle non-driving stages
            if drivingState.currentStage == DrivingStage.LOWERING_HOE:
                self.lowerHoe()
                self.advanceStage()
                continue
            if drivingState.currentStage == DrivingStage.RAISING_HOE:
                self.raiseHoe()
                self.advanceStage()
                continue
            if drivingState.currentStage == DrivingStage.STOP_CENTERING_HOE:
                self.arduinoSerial.send_command("gantry 0")
                self.advanceStage()
                continue
            if drivingState.currentStage == DrivingStage.STOP_DRIVING:
                self.arduinoSerial.send_command("drive 0 0")
                self.advanceStage()
                continue
            if drivingState.currentStage == DrivingStage.CENTERING_HOE:
                hoeIsCentered = gantryCmd is not None and gantryCmd == "gantry 0" and not lostContext
                if hoeIsCentered:
                    self.advanceStage()
                elif gantryCmd is not None:
                    self.arduinoSerial.send_command(gantryCmd)
                continue

            # Handle driving stages
            if drivingState.currentStage == DrivingStage.DRIVING_NORMAL and keepDrivingNormal:
                self.sendDriveCommand(driveCmd)
            elif drivingState.currentStage == DrivingStage.DRIVING_NORMAL and not keepDrivingNormal:
                self.advanceStage()
            elif drivingState.currentStage == DrivingStage.DRIVING_BLIND and keepDrivingBlind:
                self.sendDriveCommand(driveCmd)
            elif drivingState.currentStage == DrivingStage.DRIVING_BLIND and not keepDrivingBlind:
                self.advanceStage()

def getDriveCmd(
        cvOutputLines: CvOutputLines,
        drivingState: DrivingState,
    ) -> str:
    """
    Returns the drive command based on the left and right lines. 
    The goal is to keep robot heading in the direction of the centerline.
    The robot will drive forward at the specified speed, and adjust its steering based on the angle of the lines.
    Modified logic will apply if the robot is in reverse or if the rear camera is being used to steer.
    """
    # Unpack inputs
    leftLine = cvOutputLines.leftLine
    rightLine = cvOutputLines.rightLine
    centerLine = cvOutputLines.centerLine
    forwardSpeed = DRIVING_SPEED
    currentDrivingDirection = drivingState.drivingDirection

    if leftLine is None or rightLine is None:
        return None

    avgLine = Line.avg_line(leftLine, rightLine)
    if avgLine is None:
        return None
    
    forwardSpeed = clamp(forwardSpeed, 0, 1)
    
    minDeltaX = 2 # sets deadzone
    maxDeltaX = 100 # the maximum expected deltaX value, used to scale the steering correction

    # Use farside of avgLine to steer
    deltaX = avgLine.end.x - centerLine.end.x

    # Deadzone for steering
    if abs(deltaX) < minDeltaX:
        deltaX = 0

    # Clamp deltaX to a range to avoid extreme steering angles
    deltaX = clamp(deltaX, -maxDeltaX, maxDeltaX)

    pwmLimit = 255
    forwardPwm = pwmLimit * forwardSpeed
    forward_correction_factor = 1.5
    reverse_correction_factor = -1.0
    forward_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * forward_correction_factor
    reverse_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * reverse_correction_factor
    leftCorrection = forward_correction if deltaX > 0 else reverse_correction
    rightCorrection = reverse_correction if deltaX > 0 else forward_correction

    # left and right tank drive speeds should range from -255 to 255, with 0 representing zero velocity.
    leftSpeed = int(forwardPwm + leftCorrection)
    rightSpeed = int(forwardPwm + rightCorrection)

    if currentDrivingDirection == DrivingDirection.BACKWARD:
        leftSpeed, rightSpeed = -rightSpeed, -leftSpeed

    leftSpeed = clamp(leftSpeed, -pwmLimit, pwmLimit)
    rightSpeed = clamp(rightSpeed, -pwmLimit, pwmLimit)

    leftSpeed = str(leftSpeed)
    rightSpeed = str(rightSpeed)

    return f"drive {leftSpeed} {rightSpeed}"
    
def clamp(value, min_value, max_value):
    """
    Clamps a value between a minimum and maximum value.
    """
    return max(min(value, max_value), min_value)

def get_gantry_cmd(
        cvOutputLines: CvOutputLines,
        drivingState: DrivingState,
    ) -> str:
    """
    Returns the hoe command based on the left and right lines. The goal is to keep the hoe aligned with the centerline.
    """
    # Unpack inputs
    leftLine = cvOutputLines.leftLine
    rightLine = cvOutputLines.rightLine
    centerLine = cvOutputLines.centerLine
    currentDrivingDirection = drivingState.drivingDirection

    if leftLine is None or rightLine is None or centerLine is None:
        return None

    avgMidpointX = (leftLine.midpoint().x + rightLine.midpoint().x) // 2
    deltaX = avgMidpointX - centerLine.midpoint().x

    minDeltaX = 5 # sets deadzone
    maxDeltaX = 50 # the maximum expected deltaX value, used to scale correction

    # Deadzone
    if abs(deltaX) < minDeltaX:
        return "gantry 0"

    # stepDelay should range from maxDelay to minDelay uS, with maxDelay representing a small adjustment
    # and minDelay representing a large adjustment. 0 represents no adjustment.
    maxDelay = 20000
    minDelay = 5000
    stepDelayMag = int(maxDelay - (abs(deltaX) / maxDeltaX) * (maxDelay - minDelay))
    stepDelay = deltaX / abs(deltaX) * stepDelayMag if deltaX != 0 else 0

    if currentDrivingDirection == DrivingDirection.BACKWARD:
        stepDelay = -stepDelay

    stepDelay = str(stepDelay)
    return f"gantry {stepDelay}"