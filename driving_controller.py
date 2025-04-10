from enum import IntEnum
import threading
import time
from frame_processor import CvOutputLines, CvOutputs, Line, dont_process_frame, process_frame
from serial_comms import ArduinoSerial
from webcams import Webcams
from cv_settings import currentSettingsState, currentSettingsStateLock

TIME_UNTIL_LOST_SECONDS = 1.5
DRIVE_FROM_REARVIEW_SECONDS = 4.0
LEAVE_CURRENT_ROW_SECONDS = 3.0

class DrivingDirection:
    FORWARD = True
    BACKWARD = False

class CameraDirection:
    FRONT = True
    REAR = False

class DrivingStage(IntEnum):
    CENTERING_HOE =            0
    LOWERING_HOE =             1
    DRIVING_NORMAL =           2
    DRIVING_FROM_REARVIEW =    3
    RAISING_HOE =              4
    LEAVING_CURRENT_ROW =      5
    SEARCHING_FOR_NEXT_ROW =   6

    @classmethod
    def next(cls, current):
        members = list(cls)
        index = members.index(current)
        return members[(index + 1) % len(members)]

class DrivingState:
    def __init__(self):
        # This is meant to be mutated upon receiving messages from the arduino
        self.isAutoMode = False # This is a flag that indicates whether the robot is in auto mode or not

        # These are not intended to be mutated by controller
        self.drivingSpeed = 0.2 # This is the speed at which the robot will drive, between 0 and 1
        self.oscillating = False # This is a flag that indicates whether the robot is oscillating or not

        # These are intended to be mutated by controller
        self.overallDrivingDirection = DrivingDirection.FORWARD # This is the overall direction the robot is traveling along the row, ignoring any oscillations
        self.currentDrivingDirection = DrivingDirection.FORWARD # This is the current direction the robot is traveling in, which may be different from the overall direction if the robot is oscillating
        self.currentStage = DrivingStage.CENTERING_HOE
        self.lastStageChange = 0 # This is the last time the stage was changed, which will be used to control periodic oscillation
        self.lastHadContext = 0 # This is the last time the robot had context, which is used to determine if the robot is lost or not

class OutputState:
    def __init__(self):
        self.latestDriveCommand = None
        self.latestHoeCommand = None

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

    def reset(self):
        with self.drivingStateLock:
            self.drivingState = DrivingState()
        with self.outputStateLock:
            self.outputState = OutputState()
        with self.serialLogHistoryLock:
            self.serialLogHistory = []
        print("Resetting driving controller state")

    def advanceStage(self):
        with self.drivingStateLock:
            self.drivingState.currentStage = DrivingStage.next(self.drivingState.currentStage)
            print(f"Advancing to stage {self.drivingState.currentStage.name}")
            # This describes the stage at which the robot changes direction
            # Important to tell the robot which camera to pay attention to 
            if self.drivingState.currentStage == DrivingStage.LEAVING_CURRENT_ROW:
                self.drivingState.overallDrivingDirection = not self.drivingState.overallDrivingDirection
                self.drivingState.currentDrivingDirection = self.drivingState.overallDrivingDirection
            self.drivingState.lastStageChange = time.time()

    def handleArduinoSerialLog(self, message: str):
        print(message)

        # Only start the controller loop if the robot is in auto mode
        if "mode 0" in message:
            with self.drivingStateLock:
                self.drivingState.isAutoMode = True
        elif "mode 1" in message or "mode 2" in message:
            with self.drivingStateLock:
                self.drivingState.isAutoMode = False

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
            hoeCmd: str = None
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
                hoeCmd = get_hoe_cmd(
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
                hoeCmd = get_hoe_cmd(
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

                self.outputState.latestHoeCommand = hoeCmd
                self.outputState.frontCombinedImg = frontFrameOutput.combinedJpgTxt if frontFrameOutput else None
                self.outputState.rearCombinedImg = rearFrameOutput.combinedJpgTxt if rearFrameOutput else None

            # Do nothing if the robot is not in auto mode
            if not drivingState.isAutoMode:
                time.sleep(0.1)
                continue

            # Check if the robot is lost based on the time since it last had context
            # and the time since the last stage change
            with self.drivingStateLock:   
                isLost = time.time() - self.drivingState.lastHadContext > TIME_UNTIL_LOST_SECONDS
                timeSinceStageChange = time.time() - self.drivingState.lastStageChange
                keepDrivingFromRearview = timeSinceStageChange < DRIVE_FROM_REARVIEW_SECONDS
                keedLeavingCurrentRow = timeSinceStageChange < LEAVE_CURRENT_ROW_SECONDS

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
                if keedLeavingCurrentRow:
                    self.moveHoeRight()
                else:
                    self.advanceStage()
                self.endLoop()
                continue
            if drivingState.currentStage == DrivingStage.SEARCHING_FOR_NEXT_ROW:
                if lostContext:
                    self.moveHoeRight()
                else:
                    self.advanceStage()
                self.endLoop()
                continue
            if drivingState.currentStage == DrivingStage.CENTERING_HOE:
                if hoeCmd == "hoe 0 0" and not lostContext:
                    self.advanceStage()
                elif hoeCmd is not None:
                    self.arduinoSerial.send_command(hoeCmd)
                self.endLoop()
                continue

            # Handle driving stages
            if drivingState.currentStage == DrivingStage.DRIVING_NORMAL and not isLost:
                self.sendDriveCommand(driveCmd)
            elif drivingState.currentStage == DrivingStage.DRIVING_NORMAL and isLost:
                self.advanceStage()
            elif drivingState.currentStage == DrivingStage.DRIVING_FROM_REARVIEW and keepDrivingFromRearview:
                self.sendDriveCommand(driveCmd)
            elif drivingState.currentStage == DrivingStage.DRIVING_FROM_REARVIEW and not keepDrivingFromRearview:
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
        return None
    
    forwardSpeed = clamp(forwardSpeed, 0, 1)

    avgLine = Line.avg_line(leftLine, rightLine)
    if avgLine is None:
        return None
    
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
    #  \     |   \     <-- original avg line
    #   \    |    \
    #   
    #   ^    |-----|
    #   |       ^
    # new line  |
    #         deltaXFromStartOf...
    if steeringFromRearview:
        robotBlindspot = 0.5 # Accounts for the distance between the field of view of the front and rear cameras
        correctionFactor = 2 + robotBlindspot # Using this to extend line to the opposite side of the robot to emmulate frontview steering
        deltaXFromStartOfAvgLineToStartOfCenterLine = centerLine.start.x - avgLine.start.x
        deltaX = deltaX + deltaXFromStartOfAvgLineToStartOfCenterLine * correctionFactor # Extend the line to the opposite side of the robot
        deltaX = deltaX / correctionFactor # Scale the deltaX back down to the original range

    # Clamp deltaX to a range to avoid extreme steering angles
    deltaX = clamp(deltaX, -maxDeltaX, maxDeltaX)

    pwmLimit = 255
    forwardPwm = pwmLimit * forwardSpeed
    if currentDrivingDirection == DrivingDirection.FORWARD:
        forward_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * 2 # 2x correction for forward side (a way to steer more agressively withouy fully putting the brakes on on the other side)
        reverse_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * -1
    if currentDrivingDirection == DrivingDirection.BACKWARD:
        forward_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * 2.5 # seems to need more aggressive correction in reverse
        reverse_correction = (abs(deltaX) / maxDeltaX) * forwardPwm * -1.5
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

def get_hoe_cmd(
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
    currentDrivingDirection = drivingState.currentDrivingDirection

    if leftLine is None or rightLine is None or centerLine is None:
        return None

    avgMidpointX = (leftLine.midpoint().x + rightLine.midpoint().x) // 2
    delta = avgMidpointX - centerLine.midpoint().x

    # Deadzone
    if abs(delta) < 5:
        return "hoe 0 0"

    maxExpectedDelta = 50

    # stepDelay should range from maxDelay to minDelay uS, with maxDelay representing a small adjustment
    # and minDelay representing a large adjustment. 0 represents no adjustment.
    maxDelay = 20000
    minDelay = 5000
    stepDelayMag = int(maxDelay - (abs(delta) / maxExpectedDelta) * (maxDelay - minDelay))
    stepDelay = delta / abs(delta) * stepDelayMag if delta != 0 else 0

    if currentDrivingDirection == DrivingDirection.BACKWARD:
        stepDelay = -stepDelay

    stepDelay = str(stepDelay)
    return f"hoe {stepDelay} 0"