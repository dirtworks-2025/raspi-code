import cv2
import numpy as np
from scipy.spatial.distance import cdist

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
            borders.append(np.vstack(contours[0]))  # Store boundary pixels

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

    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.midpoint = (int((start[0] + end[0]) / 2), int((start[1] + end[1]) / 2))

def get_best_fit_line(pixels):
    """
    Computes the best fit line for a given set of pixels.
    """

    # Fit a line to the pixels (y = mx + b)
    y, x = zip(*pixels)
    m, b = np.polyfit(x, y, 1)

    # Calculate the start and end points of the line
    start = (int(min(x)), int(m * min(x) + b))
    end = (int(max(x)), int(m * max(x) + b))

    return Line(start, end)

open_kernel_size = 4
close_kernel_size = 3
distance_threshold = 10

def annotate_frame(image):
    image = cv2.resize(image, (360, 240))
    height, width = image.shape[:2]

    # Apply saturation filter
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    s_mean = cv2.mean(hsv)[1]
    lower = np.array([0, 150, 0])
    upper = np.array([179, 255, 255])
    sat_mask = cv2.inRange(hsv, lower, upper)

    # Morphological transformations to reduce noise
    denoised_mask = sat_mask.copy()
    
    open_kernel = np.ones((open_kernel_size, open_kernel_size), np.uint8)
    denoised_mask = cv2.morphologyEx(denoised_mask, cv2.MORPH_OPEN, open_kernel)

    close_kernel = np.ones((close_kernel_size, close_kernel_size), np.uint8)
    denoised_mask = cv2.morphologyEx(denoised_mask, cv2.MORPH_CLOSE, close_kernel)

    # Get the pixel islands
    mask_copy = denoised_mask.copy()
    islands = get_pixel_islands(mask_copy)

    # Draw islands in random colors
    island_mask = cv2.cvtColor(mask_copy, cv2.COLOR_GRAY2BGR)
    for pixels in islands:
        color = np.random.randint(0, 255, 3).tolist()
        for y, x in pixels:
            island_mask[y, x] = color

    # Get mask of each island's coastline
    coastline_mask = get_coastline_mask(islands, mask_copy)

    # Merge nearby islands into an archipelago
    archipelagos = merge_nearby_islands(islands, mask_copy, distance_threshold)

    # Draw archipelagos in random colors
    archipelago_mask = cv2.cvtColor(mask_copy, cv2.COLOR_GRAY2BGR)
    for pixels in archipelagos:
        color = np.random.randint(0, 255, 3).tolist()
        for y, x in pixels:
            archipelago_mask[y, x] = color

    # Get the best fit line for each archipelago
    mask_with_lines = cv2.cvtColor(mask_copy, cv2.COLOR_GRAY2BGR)
    image_with_lines = image.copy()
    lines = []
    for pixels in archipelagos:
        if len(pixels) < 100: # Skip small archipelagos
            continue
        line = get_best_fit_line(pixels)
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

    # Create a 4x2 grid of images
    first_row = np.hstack([
        image,
        cv2.cvtColor(sat_mask, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(denoised_mask, cv2.COLOR_GRAY2BGR),
        island_mask
    ])
    second_row = np.hstack([
        coastline_mask,
        archipelago_mask,
        mask_with_lines,
        image_with_lines,
    ])
    combined = np.vstack([first_row, second_row])

    return combined
