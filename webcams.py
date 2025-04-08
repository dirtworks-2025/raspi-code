import cv2

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