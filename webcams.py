import cv2

demo_video = "demo/sora_video.mp4"

import cv2

class Video:
    def __init__(self, path: str, flipped: bool = False, reversed: bool = False):
        self.path = path
        self.flipped = flipped
        self.reversed = reversed
        self.capture = cv2.VideoCapture(self.path)

        if not self.capture.isOpened():
            raise ValueError(f"Failed to open video file: {self.path}")

        self.frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))

        # Set current frame
        self.current_frame = self.frame_count - 1 if self.reversed else 0

    def get_next_frame(self, reversed: bool = False):
        actually_reversed = self.reversed if not reversed else not self.reversed
        # Set the capture to the correct frame
        self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)

        ret, frame = self.capture.read()
        if not ret:
            # If somehow failed (very rare), reset position
            self._reset_position()
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            ret, frame = self.capture.read()

        if frame is None:
            # Extra safety
            self._reset_position()
            return self.get_next_frame()

        # Flip horizontally if requested
        if self.flipped:
            frame = cv2.flip(frame, 1)  # flipCode=1 flips horizontally

        # Update frame index
        if actually_reversed:
            self.current_frame -= 1
            if self.current_frame < 0:
                self._reset_position()
        else:
            self.current_frame += 1
            if self.current_frame >= self.frame_count:
                self._reset_position()

        return frame

    def _reset_position(self):
        # Reset frame index based on direction
        self.current_frame = self.frame_count - 1 if self.reversed else 0

    def release(self):
        self.capture.release()


class Webcams:
    def __init__(self):
        self.front = Video(demo_video, flipped=False, reversed=False)
        self.rear = Video(demo_video, flipped=True, reversed=True)

    def get_front_frame(self, reversed: bool = False):
        return self.front.get_next_frame(reversed=reversed)
    
    def get_rear_frame(self, reversed: bool = False):
        return self.rear.get_next_frame(reversed=reversed)