# raspi-code

# Gmail account:
raspi.dirtworks@gmail.com
pw: dirtworks2025

# Github:
raspi-dirtworks
dirtworks2025

# Accessing the Raspberry Pi over SSH:
Option 1: Connect laptop and raspi to cellular hotspot
- Benefits: Both devices will have an internet connection
Option 2: Connect laptop to Wifi network "rowrider" hosted by raspi
- Benefits: Cell service is not required
- Password: dirtworks

Run this command:
```
ssh dirtworks@10.42.0.1
```
Password is "dirtworks"
IP address will show on raspi screen when joining a new network

Note: I like to access using the Remote Explorer tab in VS Code

# Running the server:
python -m uvicorn server:app --host 0.0.0.0 --port 8000

# Hotspot Server Address
http://10.42.0.1:8000/

# What each file is
- cv_settings.py manages the states of the sliders based on settings.json
- webcams.py manages the streams
- server.py manages the server for the website
- serial_comms.py find what port the arduino is on and connects, accepts callback functions (for rendering on the server), also defines send command
- frame_processor.py cv pipeline, process frame is the main function, outputs right line, left line, and center line for the one it is tracking. Only processes one camera side at a time.
- driving_controller.py main file.