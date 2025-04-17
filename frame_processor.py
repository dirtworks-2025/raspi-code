import base64
from typing import List, Optional
import cv2
import numpy as np
from scipy.spatial import KDTree
from pydantic import BaseModel
import random

from cv_settings import CvSettings

NUM_COLORS = 20
DEBUG_COLORS = [
    tuple(random.randint(0,255) for _ in range(3)) for _ in range(NUM_COLORS)
]

def nothing(x):
    pass

def get_pixel_islands(mask):
    """
    Uses OpenCV's connected components to extract pixel islands efficiently.
    """
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    pixel_islands = []
    for i in range(1, num_labels):  # Ignore background (label 0)
        if stats[i, cv2.CC_STAT_AREA] >= 10:  # Filter out small components
            x0, y0, w, h, _ = stats[i]
            # Extract the region of interest for the current component
            # This is more efficient than using np.where for the entire mask
            # and avoids unnecessary memory allocation
            region = labels[y0:y0+h, x0:x0+w] == i
            ys, xs = np.where(region)
            pixels = list(zip(ys + y0, xs + x0))
            pixel_islands.append(pixels)
    return pixel_islands

def merge_nearby_islands(islands, mask, distance_threshold):
    """
    Merges connected components whose closest border points are within a given distance threshold.
    """
    num_islands = len(islands)
    parent = list(range(num_islands))  # Union-Find parent array

    def find(i):
        """Find root of component i"""
        if parent[i] != i:
            parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        """Union two components"""
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_j] = root_i  # Merge into one set

    # Extract borders of each component
    borders = []
    for pixels in islands:
        coords = np.array(pixels, dtype=np.int32)
        temp_mask = np.zeros_like(mask)
        temp_mask[coords[:, 0], coords[:, 1]] = 255
        contours, _ = cv2.findContours(temp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours:
            borders.append(np.vstack(contours[0]))
        else:
            borders.append(np.empty((0, 1, 2), dtype=np.int32))

    for i in range(num_islands):
        for j in range(i + 1, num_islands):
            if borders[i].size == 0 or borders[j].size == 0:
                continue
            tree = KDTree(borders[i].reshape(-1, 2))
            dists, _ = tree.query(borders[j].reshape(-1, 2), k=1)
            min_dist = np.min(dists)
            if min_dist < distance_threshold:
                union(i, j)

    merged_archipelagos = {}
    for i in range(num_islands):
        root = find(i)
        if root not in merged_archipelagos:
            merged_archipelagos[root] = []
        merged_archipelagos[root].extend(islands[i])

    return list(merged_archipelagos.values())

class Point(BaseModel):
    x: int
    y: int

    def to_tuple(self):
        return (self.x, self.y)

class Line(BaseModel):
    start: Point
    end: Point
    r2: float = None

    def midpoint(self) -> Point:
        """
        Returns the midpoint of the line.
        """
        return Point(
            x=int((self.start.x + self.end.x) / 2),
            y=int((self.start.y + self.end.y) / 2)
        )

    def invert(self) -> None:
        """
        Inverts the line by swapping start and end points. Mutates the line.
        """
        self.start, self.end = self.end, self.start
    
    def scaled(self, scale_factor: float):
        """
        Returns the scaled line, still centered at the same midpoint.
        """
        start = Point(
            x=int(self.midpoint().x - (self.midpoint().x - self.start.x) * scale_factor),
            y=int(self.midpoint().y - (self.midpoint().y - self.start.y) * scale_factor)
        )
        end = Point(
            x=int(self.midpoint().x - (self.midpoint().x - self.end.x) * scale_factor),
            y=int(self.midpoint().y - (self.midpoint().y - self.end.y) * scale_factor)
        )
        return Line(start=start, end=end)
    
    def angle(self):
        """
        Returns the angle of the line in degrees.
        """
        delta_x = self.end.x - self.start.x
        delta_y = self.end.y - self.start.y
        return np.degrees(np.arctan2(delta_y, delta_x))
    
    def length(self):
        """
        Returns the length of the line.
        """
        return np.hypot(self.end.x - self.start.x, self.end.y - self.start.y)

    @classmethod
    def avg_line(cls, line1: 'Line', line2: 'Line'):
        """
        Returns the average line between two lines.
        """
        start = Point(
            x=int((line1.start.x + line2.start.x) / 2),
            y=int((line1.start.y + line2.start.y) / 2)
        )
        end = Point(
            x=int((line1.end.x + line2.end.x) / 2),
            y=int((line1.end.y + line2.end.y) / 2)
        )
        return Line(start=start, end=end)

def get_best_fit_line(pixels):
    """
    Computes the best fit line for a given set of pixels.
    """

    # Fit a line to the pixels (x = my + b)
    y, x = zip(*pixels)
    coeffs, res, _, _, _ = np.polyfit(y, x, 1, full=True)
    m, b = coeffs

    # Get the R^2 value
    r2 = 1 - (res / np.sum((y - np.mean(y)) ** 2))

    # Calculate the start and end points of the line
    start = Point(x=int(m * min(y) + b), y=int(min(y)))
    end = Point(x=int(m * max(y) + b), y=int(max(y)))

    # Enfore that the start point is always the bottom of the line (closer to the camera)
    if start.y < end.y:
        start, end = end, start

    return Line(start=start, end=end, r2=r2)

class CvOutputLines(BaseModel):
    leftLine: Optional[Line]
    rightLine: Optional[Line]
    centerLine: Optional[Line]

class CvOutputs(BaseModel):
    combinedJpgTxt: str
    outputLines: CvOutputLines
    lostContext: bool

def process_frame(image: np.ndarray, settings: CvSettings) -> CvOutputs:
    """
    Processes a single frame of the video stream."
    """
    image = cv2.resize(image, (270, 180))
    height, width = image.shape[:2]

    # Convert to HSV and split channels
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h_channel, s_channel, v_channel = cv2.split(hsv)

    # Create ROI mask (lower half of the image)
    roi_mask = np.zeros((height, width), dtype=np.uint8)
    roi_mask[height // 2:, :] = 255  # Lower half

    # Use ROI to mask each channel
    roi_h = h_channel[roi_mask == 255]
    roi_s = s_channel[roi_mask == 255]
    roi_v = v_channel[roi_mask == 255]

    # Compute percentiles on ROI only
    minH = np.percentile(roi_h, settings.hLowerPercentile)
    maxH = np.percentile(roi_h, settings.hUpperPercentile)
    minS = np.percentile(roi_s, settings.sLowerPercentile)
    maxS = np.percentile(roi_s, settings.sUpperPercentile)
    minV = np.percentile(roi_v, settings.vLowerPercentile)
    maxV = np.percentile(roi_v, settings.vUpperPercentile)

    # Create masks based on thresholds
    hue_mask = cv2.inRange(h_channel, minH, maxH)
    sat_mask = cv2.inRange(s_channel, minS, maxS)
    val_mask = cv2.inRange(v_channel, minV, maxV)

    # Overlay masks onto original channels for visualization
    # Any pixel included in the respective mask should be painted green in the original channel
    h_channel_colored = cv2.cvtColor(h_channel, cv2.COLOR_GRAY2BGR)
    s_channel_colored = cv2.cvtColor(s_channel, cv2.COLOR_GRAY2BGR)
    v_channel_colored = cv2.cvtColor(v_channel, cv2.COLOR_GRAY2BGR)
    h_channel_colored[hue_mask > 0] = (0, 165, 255)
    s_channel_colored[sat_mask > 0] = (0, 165, 255)
    v_channel_colored[val_mask > 0] = (0, 165, 255)

    # Combine masks and apply ROI again
    combined_mask = cv2.bitwise_and(hue_mask, cv2.bitwise_and(sat_mask, val_mask))
    combined_mask = cv2.bitwise_and(combined_mask, roi_mask)

    # Morphological transformations to reduce noise
    denoised_mask = combined_mask.copy()

    open_kernel = np.ones((settings.closeKernel, settings.closeKernel), np.uint8)
    denoised_mask = cv2.morphologyEx(denoised_mask, cv2.MORPH_OPEN, open_kernel)

    close_kernel = np.ones((settings.closeKernel, settings.closeKernel), np.uint8)
    denoised_mask = cv2.morphologyEx(denoised_mask, cv2.MORPH_CLOSE, close_kernel)

    # This kernel connects pixels vertically, which is useful for near-vertical line detection
    dilate_kernel = np.array([
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
    ], dtype=np.uint8)
    denoised_mask = cv2.dilate(denoised_mask, dilate_kernel, iterations=settings.verticalDilationIterations)

    # Get the pixel islands
    mask_copy = denoised_mask.copy()
    islands = get_pixel_islands(mask_copy)

    # Merge nearby islands into an archipelago
    archipelagos = merge_nearby_islands(islands, mask_copy, settings.distThreshold)

    # Draw archipelagos in random colors for debugging
    archipelago_mask = cv2.cvtColor(mask_copy, cv2.COLOR_GRAY2BGR)
    for idx, pixels in enumerate(archipelagos):
        color = DEBUG_COLORS[idx % NUM_COLORS]
        for y, x in pixels:
            archipelago_mask[y, x] = color

    # Get the best fit line for each archipelago
    mask_with_lines = cv2.cvtColor(mask_copy, cv2.COLOR_GRAY2BGR)
    image_with_lines = image.copy()
    lines: List[Line] = []
    for pixels in archipelagos:
        if len(pixels) < 100: # Skip small archipelagos
            continue
        line = get_best_fit_line(pixels)
        if abs(line.angle() + 90) > 45:  # Filter out lines too far from vertical
            continue
        if line.length() < 70:  # Filter out lines that are too short
            continue
        if line.r2 < (settings.r2Threshold / 100):  # Filter out lines with low R^2 value
            continue
        lines.append(line)

    # Sort lines by x-coordinate of midpoint
    lines.sort(key=lambda line: line.midpoint().x)

    # Determines the indices of the two lines closest to the image centerline on each side
    right_line_index = -1
    left_line_index = -1

    for idx, line in enumerate(lines):
        if line.midpoint().x > width / 2:
            right_line_index = idx
            left_line_index = idx - 1
            break

    # Draw lines on the mask and original image
    # Two lines closest to image centerline are colored green
    for idx, line in enumerate(lines):
        color = (0, 255, 0) if idx == right_line_index or idx == left_line_index else (0, 0, 255)
        cv2.line(mask_with_lines, line.start.to_tuple(), line.end.to_tuple(), color, 2)
        cv2.line(image_with_lines, line.start.to_tuple(), line.end.to_tuple(), color, 2)

    # Add a grey/white line at the image vertical centerline
    centerLine = Line(
        start=Point(x=int(width / 2), y=height),
        end=Point(x=int(width / 2), y=0),
    )
    cv2.line(mask_with_lines, centerLine.start.to_tuple(), centerLine.end.to_tuple(), (128, 128, 128), 2)
    cv2.line(image_with_lines, centerLine.start.to_tuple(), centerLine.end.to_tuple(), (255, 255, 255), 2)

    # Create a 4x3 grid of images
    placeholder = np.zeros((height, width, 3), dtype=np.uint8)
    first_row = np.hstack([
        image,
        h_channel_colored,
        s_channel_colored,
        v_channel_colored,
    ])
    second_row = np.hstack([
        cv2.cvtColor(combined_mask, cv2.COLOR_GRAY2BGR),
        archipelago_mask,
        mask_with_lines,
        image_with_lines,
    ])
    combined = np.vstack([first_row, second_row])

    # Encode the combined image to JPEG format
    _, buffer = cv2.imencode('.jpg', combined, [cv2.IMWRITE_JPEG_QUALITY, 50])
    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
    jpg_as_text = f"data:image/jpeg;base64,{jpg_as_text}"

    lostContext = left_line_index < 0 or right_line_index < 0

    outputLines = CvOutputLines(
        leftLine=lines[left_line_index] if left_line_index >= 0 else None,
        rightLine=lines[right_line_index] if right_line_index >= 0 else None,
        centerLine=centerLine,
    )

    outputs = CvOutputs(
        combinedJpgTxt=jpg_as_text,
        outputLines=outputLines,
        lostContext=lostContext,
    )
    return outputs

def dont_process_frame(image: np.ndarray) -> CvOutputs:
    """
    Pads the image with placeholders to create a 4x3 grid.
    This allows the unprocessed images to still be displayed in the web interface.
    """
    height, width = image.shape[:2]
    placeholder = np.zeros((height, width, 3), dtype=np.uint8)
    first_row = np.hstack([image, placeholder, placeholder, placeholder])
    second_row = np.hstack([placeholder, placeholder, placeholder, placeholder])
    combined = np.vstack([first_row, second_row])
    
    # Encode the combined image to JPEG format
    _, buffer = cv2.imencode('.jpg', combined, [cv2.IMWRITE_JPEG_QUALITY, 20])
    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
    jpg_as_text = f"data:image/jpeg;base64,{jpg_as_text}"
    return CvOutputs(
        combinedJpgTxt=jpg_as_text,
        outputLines=CvOutputLines(
            leftLine=None,
            rightLine=None,
            centerLine=None,
        ),
        lostContext=True,
    )