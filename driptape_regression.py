import cv2
import numpy as np
from scipy.spatial.distance import cdist
from pydantic import BaseModel

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
            y, x = np.where(labels == i)
            pixels = list(zip(y, x))
            pixel_islands.append(pixels)
    
    return pixel_islands

def get_coastline_mask(islands, mask):
    """
    Extracts the coastlines of each connected component. Returns a binary mask with coastlines colored randomly.
    """
    coastline_mask_grayscale = np.zeros_like(mask)
    coastline_mask = cv2.cvtColor(coastline_mask_grayscale, cv2.COLOR_GRAY2BGR)
    for pixels in islands:
        temp_mask = np.zeros_like(mask)
        for y, x in pixels:
            temp_mask[y, x] = 255  # Fill pixels for current component

        contours, _ = cv2.findContours(temp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        random_color = np.random.randint(0, 255, 3).tolist()
        if contours:
            cv2.drawContours(coastline_mask, contours, -1, random_color, 1)

    return coastline_mask

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
        temp_mask = np.zeros_like(mask)
        for y, x in pixels:
            temp_mask[y, x] = 255  # Fill pixels for current component

        contours, _ = cv2.findContours(temp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours:
            borders.append(np.vstack(contours[0]))  # Store boundary pixels for each component

    # Compute pairwise distances between component borders
    for i in range(num_islands):
        for j in range(i + 1, num_islands):
            if len(borders[i]) == 0 or len(borders[j]) == 0:
                continue  # Skip if no border detected
            dist_matrix = cdist(borders[i], borders[j])  # Compute all pairwise distances
            min_dist = np.min(dist_matrix)

            if min_dist < distance_threshold:
                union(i, j)

    # Group components based on final merged sets
    merged_archipelagos = {}
    for i in range(num_islands):
        root = find(i)
        if root not in merged_archipelagos:
            merged_archipelagos[root] = []
        merged_archipelagos[root].extend(islands[i])

    return list(merged_archipelagos.values())

class Line:
    start = None
    end = None
    midpoint = None
    r2 = None

    def __init__(self, start, end, r2=None):
        self.start = start
        self.end = end
        self.midpoint = (int((start[0] + end[0]) / 2), int((start[1] + end[1]) / 2))
        self.r2 = r2

    def inverted(self):
        """
        Returns the inverted line.
        """
        return Line(self.end, self.start)
    
    def scaled(self, scale_factor: float):
        """
        Returns the scaled line, still centered at the same midpoint.
        """
        start = (int(self.midpoint[0] - (self.midpoint[0] - self.start[0]) * scale_factor),
                 int(self.midpoint[1] - (self.midpoint[1] - self.start[1]) * scale_factor))
        end = (int(self.midpoint[0] - (self.midpoint[0] - self.end[0]) * scale_factor),
               int(self.midpoint[1] - (self.midpoint[1] - self.end[1]) * scale_factor))
        return Line(start, end)
    
    def angle(self):
        """
        Returns the angle of the line in degrees.
        """
        delta_x = self.end[0] - self.start[0]
        delta_y = self.end[1] - self.start[1]
        return np.degrees(np.arctan2(delta_y, delta_x))
    
    def length(self):
        """
        Returns the length of the line.
        """
        return np.sqrt((self.end[0] - self.start[0]) ** 2 + (self.end[1] - self.start[1]) ** 2)

    @classmethod
    def avg_line(cls, line1: 'Line', line2: 'Line'):
        """
        Returns the average line between two lines.
        """
        start = (int((line1.start[0] + line2.start[0]) / 2), int((line1.start[1] + line2.start[1]) / 2))
        end = (int((line1.end[0] + line2.end[0]) / 2), int((line1.end[1] + line2.end[1]) / 2))
        return Line(start, end)

def get_best_fit_line(pixels):
    """
    Computes the best fit line for a given set of pixels.
    """

    # Fit a line to the pixels (x = my + b)
    y, x = zip(*pixels)
    coeffs, res, _, _, _ = np.polyfit(y, x, 1, full=True)
    m, b = coeffs

    # Get the R^2 value
    r2 = 1 - (res / np.sum((x - np.mean(x)) ** 2))

    # Calculate the start and end points of the line
    start = (int(m * min(y) + b), int(min(y)))
    end = (int(m * max(y) + b), int(max(y)))

    return Line(start, end, r2)

class AnnotationSettings(BaseModel):
    minH: int
    maxH: int
    minS: int
    maxS: int
    minV: int
    maxV: int
    closeKernel: int
    openKernel: int
    distThreshold: int

def annotate_frame(image, settings: AnnotationSettings):
    image = cv2.resize(image, (360, 240))
    height, width = image.shape[:2]

    # Apply HSV filters
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h_channel, s_channel, v_channel = cv2.split(hsv)

    lower = np.array([settings.minH, 0, 0])
    upper = np.array([settings.maxH, 255, 255])
    hue_mask = cv2.inRange(hsv, lower, upper)

    lower = np.array([0, settings.minS, 0])
    upper = np.array([179, settings.maxS, 255])
    sat_mask = cv2.inRange(hsv, lower, upper)

    lower = np.array([0, 0, settings.minV])
    upper = np.array([179, 255, settings.maxV])
    val_mask = cv2.inRange(hsv, lower, upper)

    combined_mask = cv2.bitwise_and(hue_mask, cv2.bitwise_and(sat_mask, val_mask))

    # Morphological transformations to reduce noise
    denoised_mask = combined_mask.copy()

    # This kernel connects pixels vertically, which is useful for near-vertical line detection
    dilate_kernel = np.array([
        [0, 1, 0],
        [0, 1, 0],
        [0, 1, 0]
    ], dtype=np.uint8)
    denoised_mask = cv2.dilate(denoised_mask, dilate_kernel, iterations=2)

    open_kernel = np.ones((settings.closeKernel, settings.closeKernel), np.uint8)
    denoised_mask = cv2.morphologyEx(denoised_mask, cv2.MORPH_OPEN, open_kernel)

    close_kernel = np.ones((settings.closeKernel, settings.closeKernel), np.uint8)
    denoised_mask = cv2.morphologyEx(denoised_mask, cv2.MORPH_CLOSE, close_kernel)

    # Get the pixel islands
    mask_copy = denoised_mask.copy()
    islands = get_pixel_islands(mask_copy)

    # Merge nearby islands into an archipelago
    archipelagos = merge_nearby_islands(islands, mask_copy, settings.distThreshold)

    # Draw archipelagos in random colors - not used in final image, but useful for debugging
    archipelago_mask = cv2.cvtColor(mask_copy, cv2.COLOR_GRAY2BGR)
    for pixels in archipelagos:
        color = np.random.randint(0, 255, 3).tolist()
        for y, x in pixels:
            archipelago_mask[y, x] = color

    # Get the best fit line for each archipelago
    mask_with_lines = cv2.cvtColor(mask_copy, cv2.COLOR_GRAY2BGR)
    steering_arrow = cv2.cvtColor(np.zeros_like(mask_copy), cv2.COLOR_GRAY2BGR)
    image_with_lines = image.copy()
    lines = []
    for pixels in archipelagos:
        if len(pixels) < 100: # Skip small archipelagos
            continue
        line = get_best_fit_line(pixels)
        if line.angle() < 30:  # Filter out lines that are too horizontal
            continue
        if line.length() < 20:  # Filter out lines that are too short
            continue
        if line.r2 < 0.5:  # Filter out lines with low R^2 value
            continue # TODO: verify this works
        lines.append(line)

    # Sort lines by x-coordinate of midpoint
    lines.sort(key=lambda line: line.midpoint[0])

    # Determines the indices of the two lines closest to the image centerline on each side
    right_line_index = 0
    left_line_index = 0

    for idx, line in enumerate(lines):
        if line.midpoint[0] > width / 2:
            right_line_index = idx
            left_line_index = idx - 1
            break

    # Draw lines on the mask and original image
    # Two lines closest to image centerline are colored green
    for idx, line in enumerate(lines):
        color = (0, 255, 0) if idx == right_line_index or idx == left_line_index else (0, 0, 255)
        cv2.line(mask_with_lines, line.start, line.end, color, 2)
        cv2.line(image_with_lines, line.start, line.end, color, 2)

    # Add a grey/white line at the image vertical centerline
    cv2.line(mask_with_lines, (width // 2, 0), (width // 2, height), (128, 128, 128), 2)
    cv2.line(image_with_lines, (width // 2, 0), (width // 2, height), (255, 255, 255), 2)

    # Draw arrow representing steering correction
    if left_line_index >= 0 and right_line_index < len(lines):
        average_line = Line.avg_line(lines[right_line_index].inverted(), lines[left_line_index].inverted()).scaled(0.5)
        cv2.arrowedLine(steering_arrow, (width // 2, height), average_line.end, (255, 255, 255), 2)

    # Create a 4x3 grid of images
    placeholder = np.zeros((height, width, 3), dtype=np.uint8)
    first_row = np.hstack([
        image,
        cv2.cvtColor(h_channel, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(s_channel, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(v_channel, cv2.COLOR_GRAY2BGR),
    ])
    second_row = np.hstack([
        cv2.cvtColor(combined_mask, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(denoised_mask, cv2.COLOR_GRAY2BGR),
        archipelago_mask,
        mask_with_lines,
    ])
    third_row = np.hstack([
        image_with_lines,
        steering_arrow,
        placeholder,
        placeholder,
    ])
    combined = np.vstack([first_row, second_row, third_row])

    return combined
