import tkinter as tk
import cv2
from PIL import Image, ImageTk

# Initialize the two webcam captures (usually 0 and 1 for two webcams)
cap1 = cv2.VideoCapture(0)
cap2 = cv2.VideoCapture(2)

def update_video():
    # Capture frames from both cameras
    ret1, frame1 = cap1.read()
    ret2, frame2 = cap2.read()
    # testing

    if ret1 and ret2:
        # Convert frames to RGB (OpenCV uses BGR by default)
        frame1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
        frame2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2RGB)
        
        # Convert the images to a format suitable for Tkinter
        img1 = ImageTk.PhotoImage(image=Image.fromarray(frame1))
        img2 = ImageTk.PhotoImage(image=Image.fromarray(frame2))

        # Update the labels with the new images
        label1.config(image=img1)
        label1.image = img1
        label2.config(image=img2)
        label2.image = img2

    # Call this function again after a delay
    root.after(10, update_video)

# Create the main window
root = tk.Tk()
root.title("Dual Webcam Display")

# Create two labels to hold the webcam video
label1 = tk.Label(root)
label1.pack(side="left", padx=10)

label2 = tk.Label(root)
label2.pack(side="right", padx=10)

# Start updating the video frames
update_video()

# Start the Tkinter event loop
root.mainloop()

# Release the webcam resources when done
cap1.release()
cap2.release()
