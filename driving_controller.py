import threading
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

class DrivingStage:
    LOWERING_HOE = 0
    DRIVING_NORMAL = 1
    DRIVING_FROM_REARVIEW = 2
    RAISING_HOE = 3
    LEAVING_CURRENT_ROW = 4
    SEARCHING_FOR_NEXT_ROW = 5

class DrivingState:
    def __init__(self):
        self.drivingSpeed = 0.2 # This is the speed at which the robot will drive forward, between 0 and 1
        self.overallDrivingDirection = DrivingDirection.FORWARD # This is the overall direction the robot is traveling along the row, ignoring any oscillations
        self.currentDrivingDirection = DrivingDirection.FORWARD # This is the current direction the robot is traveling in, which may be different from the overall direction if the robot is oscillating
        self.oscillating = False
        self.currentStage = DrivingStage.LOWERING_HOE
        self.lastStageChange = 0

class OutputState:
    def __init__(self):
        self.latestDriveCommand = None
        self.frontCombinedImg = None
        self.rearCombinedImg = None
        self.frontLostContext = False
        self.rearLostContext = False
    
class DrivingController:
    def __init__(self):
        self.lock = threading.Lock()

        self.drivingState = DrivingState()
        self.outputState = OutputState()

        self.serialLogHistory = []
        self.arduinoSerial = ArduinoSerial(self.handleArduinoSerialLog)

        threading.Thread(target=self.controllerLoop, daemon=True).start()

    def advanceStage(self):
        with self.lock:
            self.currentStage = (self.currentStage + 1) % 6

    def handleArduinoSerialLog(self, message: str):
        print(message)
        with self.lock:
            self.serialLogHistory.append(message)
            if len(self.serialLogHistory) > 100:
                self.serialLogHistory.pop(0)
    
    def controllerLoop(self):
        webcams = Webcams()
        while True:
            # Get a snapshot of the current settings and the current state of the controller
            with currentSettingsStateLock:
                settingsSnapshot = currentSettingsState.settings
            with self.lock:
                drivingState = self.drivingState

            # Get the current frames from the webcams
            maybeSwapped = settingsSnapshot.swapCameras
            frontFrame = webcams.get_front_frame(maybeSwapped)
            rearFrame = webcams.get_rear_frame(maybeSwapped)

            # Determine which camera to process based on the current stage and driving direction
            cameraToProcess = drivingState.currentDrivingDirection
            if drivingState.currentStage == DrivingStage.DRIVING_FROM_REARVIEW:
                cameraToProcess = not drivingState.currentDrivingDirection

            # Process the frames to get the lines, combined images, and drive commands
            driveCmd: str = None
            frontFrameOutput: CvOutputs = None
            rearFrameOutput: CvOutputs = None
            
            if frontFrame is not None and cameraToProcess == CameraDirection.FRONT:
                frontFrameOutput = process_frame(frontFrame)
                driveCmd = getDriveCmd(
                    cvOutputLines=frontFrameOutput.outputLines,
                    drivingState=drivingState,
                )
            elif frontFrame is not None and cameraToProcess == CameraDirection.REAR:
                frontFrameOutput = dont_process_frame(frontFrame)
            
            if rearFrame is not None and cameraToProcess == CameraDirection.REAR:
                rearFrameOutput = process_frame(rearFrame)
                driveCmd = getDriveCmd(
                    cvOutputLines=rearFrameOutput.outputLines,
                    drivingState=drivingState,
                )
            elif rearFrame is not None and cameraToProcess == CameraDirection.FRONT:
                rearFrameOutput = dont_process_frame(rearFrame)

            # Update the output state with the processed frames and drive command
            with self.lock:
                self.outputState.latestDriveCommand = driveCmd
                self.outputState.frontCombinedImg = frontFrameOutput.combinedJpgTxt if frontFrameOutput else None
                self.outputState.rearCombinedImg = rearFrameOutput.combinedJpgTxt if rearFrameOutput else None
                self.outputState.frontLostContext = frontFrameOutput.lostContext if frontFrameOutput else False
                self.outputState.rearLostContext = rearFrameOutput.lostContext if rearFrameOutput else False

            # Maybe send the drive command to the Arduino
            if driveCmd is not None:
                with self.lock:
                    self.arduinoSerial.send_command(driveCmd)

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