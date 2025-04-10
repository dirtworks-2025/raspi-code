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

Run this command:
```
ssh dirtworks@10.42.0.1
```
Password is "dirtworks"
IP address will show on raspi screen when joining a new network

Note: I like to access using the Remote Explorer tab in VS Code

# Running the server:
python -m uvicorn server:app --host 0.0.0.0 --port 8000