from enum import IntEnum
import threading
import time
from frame_processor import CvOutputLines, CvOutputs, Line, dont_process_frame, process_frame
from serial_comms import ArduinoSerial
from webcams import Webcams
from cv_settings import currentSettingsState, currentSettingsStateLock

class DrivingDirection:
    FORWARD = True
    BACKWARD = False

class CameraDirection:
    FRONT = True
    REAR = False

class DrivingStage(IntEnum):
    LOWERING_HOE = 0
    DRIVING_NORMAL = 1
    DRIVING_FROM_REARVIEW = 2
    RAISING_HOE = 3
    LEAVING_CURRENT_ROW = 4
    SEARCHING_FOR_NEXT_ROW = 5

    @classmethod
    def next(cls, current):
        members = list(cls)
        index = members.index(current)
        return members[(index + 1) % len(members)]

class DrivingState:
    def __init__(self):
        # These are not intended to be mutated by controller
        self.drivingSpeed = 0.2 # This is the speed at which the robot will drive, between 0 and 1
        self.oscillating = False # This is a flag that indicates whether the robot is oscillating or not

        # These are intended to be mutated by controller
        self.overallDrivingDirection = DrivingDirection.FORWARD # This is the overall direction the robot is traveling along the row, ignoring any oscillations
        self.currentDrivingDirection = DrivingDirection.FORWARD # This is the current direction the robot is traveling in, which may be different from the overall direction if the robot is oscillating
        self.currentStage = DrivingStage.LOWERING_HOE
        self.lastStageChange = 0 # This is the last time the stage was changed, which will be used to control periodic oscillation
        self.lastHadContext = 0 # This is the last time the robot had context, which is used to determine if the robot is lost or not

class OutputState:
    def __init__(self):
        self.latestDriveCommand = None
        self.frontCombinedImg = None
        self.rearCombinedImg = None
        self.frontLostContext = False
        self.rearLostContext = False
    
class DrivingController:
    def __init__(self):
        self.finishedProcessing = threading.Event()

        self.drivingState = DrivingState()
        self.drivingStateLock = threading.Lock()
        self.outputState = OutputState()
        self.outputStateLock = threading.Lock()

        self.serialLogHistory = []
        self.serialLogHistoryLock = threading.Lock()
        self.arduinoSerial = ArduinoSerial(self.handleArduinoSerialLog)

        threading.Thread(target=self.controllerLoop, daemon=True).start()

    def advanceStage(self):
        with self.drivingStateLock:
            self.drivingState.currentStage = DrivingStage.next(self.drivingState.currentStage)
            # Maybe switch directions
            if self.drivingState.currentStage == DrivingStage.LOWERING_HOE:
                self.drivingState.overallDrivingDirection = not self.drivingState.overallDrivingDirection
            self.drivingState.lastStageChange = time.time()

    def handleArduinoSerialLog(self, message: str):
        print(message)
        with self.serialLogHistoryLock:
            self.serialLogHistory.append(message)
            if len(self.serialLogHistory) > 100:
                self.serialLogHistory.pop(0)

    def raiseHoe(self):
        self.arduinoSerial.send_command("drive 0 0")
        time.sleep(0.1)
        self.arduinoSerial.send_command("hoe up")
        time.sleep(2)
    
    def lowerHoe(self):
        self.arduinoSerial.send_command("hoe 0 0")
        time.sleep(0.1)
        self.arduinoSerial.send_command("hoe down")
        time.sleep(2)

    def moveHoeRight(self):
        self.arduinoSerial.send_command("hoe 10000 0")
        time.sleep(0.1)

    def sendDriveCommand(self, driveCmd: str):
        if driveCmd is None:
            return
        self.arduinoSerial.send_command(driveCmd)

    def endLoop(self):
        self.finishedProcessing.set()
        # time.sleep(0.1)

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
            cameraToProcess = drivingState.currentDrivingDirection
            if drivingState.currentStage == DrivingStage.DRIVING_FROM_REARVIEW:
                cameraToProcess = not drivingState.currentDrivingDirection

            # Process the frames to get the lines, combined images, and drive commands
            driveCmd: str = None
            lostContext: bool = False
            frontFrameOutput: CvOutputs = None
            rearFrameOutput: CvOutputs = None
            
            if frontFrame is not None and cameraToProcess == CameraDirection.FRONT:
                frontFrameOutput = process_frame(frontFrame, settings)
                lostContext = frontFrameOutput.lostContext
                with self.outputStateLock:
                    self.outputState.frontLostContext = lostContext
                driveCmd = getDriveCmd(
                    cvOutputLines=frontFrameOutput.outputLines,
                    drivingState=drivingState,
                )
            elif frontFrame is not None and cameraToProcess == CameraDirection.REAR:
                frontFrameOutput = dont_process_frame(frontFrame)
            
            if rearFrame is not None and cameraToProcess == CameraDirection.REAR:
                rearFrameOutput = process_frame(rearFrame, settings)
                lostContext = rearFrameOutput.lostContext
                with self.outputStateLock:
                    self.outputState.rearLostContext = lostContext
                driveCmd = getDriveCmd(
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
                self.outputState.latestDriveCommand = driveCmd
                self.outputState.frontCombinedImg = frontFrameOutput.combinedJpgTxt if frontFrameOutput else None
                self.outputState.rearCombinedImg = rearFrameOutput.combinedJpgTxt if rearFrameOutput else None

            # Handle non-driving stages
            if drivingState.currentStage == DrivingStage.LOWERING_HOE:
                self.lowerHoe()
                self.advanceStage()
                self.endLoop()
                continue
            if drivingState.currentStage == DrivingStage.RAISING_HOE:
                self.raiseHoe()
                self.advanceStage()
                self.endLoop()
                continue
            if drivingState.currentStage == DrivingStage.LEAVING_CURRENT_ROW:
                if lostContext:
                    self.advanceStage()
                else:
                    self.moveHoeRight()
                self.endLoop()
                continue
            if drivingState.currentStage == DrivingStage.SEARCHING_FOR_NEXT_ROW:
                if lostContext:
                    self.moveHoeRight()
                else:
                    self.advanceStage()
                self.endLoop()
                continue

            # Handle driving stages
            with self.drivingStateLock:   
                isLost = time.time() - self.drivingState.lastHadContext > 1.5
            
            if drivingState.currentStage == DrivingStage.DRIVING_NORMAL and not isLost:
                self.sendDriveCommand(driveCmd)
            elif drivingState.currentStage == DrivingStage.DRIVING_NORMAL and isLost:
                self.advanceStage()
            elif drivingState.currentStage == DrivingStage.DRIVING_FROM_REARVIEW and not isLost:
                self.sendDriveCommand(driveCmd)
            elif drivingState.currentStage == DrivingStage.DRIVING_FROM_REARVIEW and isLost:
                self.advanceStage()

            self.endLoop()

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
    forwardSpeed = drivingState.drivingSpeed
    currentDrivingDirection = drivingState.currentDrivingDirection
    steeringFromRearview = drivingState.currentDrivingDirection == DrivingStage.DRIVING_FROM_REARVIEW

    if leftLine is None or rightLine is None:
        return "drive 0 0"
    
    forwardSpeed = clamp(forwardSpeed, 0, 1)

    avgLine = Line.avg_line(leftLine, rightLine)
    if avgLine is None:
        return "drive 0 0"
    
    minDeltaX = 5
    maxDeltaX = 100

    # Use farside of avgLine to steer
    deltaX = avgLine.end.x - centerLine.end.x

    # Deadzone for steering
    if abs(deltaX) < minDeltaX:
        deltaX = 0

    # Handle rearview steering
    #
    # \      |  \ 
    #  \     |   \     <-- original line
    #   \    |    \
    #   
    #   ^    |-----|
    #   |       ^
    # new line  |
    #         deltaX
    if steeringFromRearview:
        robotBlindspot = 0.5 # Accounts for the distance between the field of view of the front and rear cameras
        correctionFactor = 2 + robotBlindspot # Using this to extend line to the opposite side of the robot to emmulate frontview steering
        deltaXFromStartOfAvgLineToStartOfCenterLine = avgLine.start.x - centerLine.start.x
        deltaX = deltaX + deltaXFromStartOfAvgLineToStartOfCenterLine * correctionFactor # Extend the line to the opposite side of the robot
        deltaX = deltaX / correctionFactor # Scale the deltaX back down to the original range

    # Clamp deltaX to a range to avoid extreme steering angles
    deltaX = clamp(deltaX, -maxDeltaX, maxDeltaX)

    pwmLimit = 255
    forwardPwm = pwmLimit * forwardSpeed
    forward_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * 2 # 2x correction for forward side (a way to steer more agressively withouy fully putting the brakes on on the other side)
    reverse_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * -1
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