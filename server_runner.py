"""
Server standalone entrypoint for PyInstaller.
"""

import os
import sys
import webbrowser
import threading
import time

# Ensure static files directory is found in PyInstaller bundle
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

os.environ["IT_CLASS_BUNDLE_DIR"] = bundle_dir

import uvicorn
import main

def open_browser():
    time.sleep(1.8)
    webbrowser.open("http://127.0.0.1:8023")

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(main.app, host="127.0.0.1", port=8023, log_level="info")
