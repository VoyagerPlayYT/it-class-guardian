"""
Automated PyInstaller Build Script for IT-Class Guardian.
Compiles standalone .exe binaries without requiring Python on target machines.
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"

def build():
    print("==================================================")
    print("   BUILDING IT-CLASS GUARDIAN STANDALONE EXES     ")
    print("==================================================")

    py = sys.executable

    # 1. Build Student Agent
    print("\n[1/3] Compiling Student Agent (Агент_Ученика.exe)...")
    cmd_agent = [
        py, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--uac-admin",
        "--name", "Агент_Ученика",
        str(BASE_DIR / "student_agent.py")
    ]
    subprocess.run(cmd_agent, cwd=BASE_DIR, check=True)

    # 2. Build Teacher Server Console
    print("\n[2/3] Compiling Teacher Server (Учитель_Панель.exe)...")
    cmd_server = [
        py, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--add-data", f"{BASE_DIR / 'static'};static",
        "--name", "Учитель_Панель",
        str(BASE_DIR / "server_runner.py")
    ]
    subprocess.run(cmd_server, cwd=BASE_DIR, check=True)

    # 3. Build Unified Installer
    print("\n[3/3] Compiling Setup Installer (Установщик_Классный_Страж.exe)...")
    cmd_installer = [
        py, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--uac-admin",
        "--name", "Установщик_Классный_Страж",
        str(BASE_DIR / "installer.py")
    ]
    subprocess.run(cmd_installer, cwd=BASE_DIR, check=True)

    print("\n==================================================")
    print("   SUCCESS! All 3 executables built in /dist:     ")
    print("   - dist/Агент_Ученика.exe                      ")
    print("   - dist/Учитель_Панель.exe                     ")
    print("   - dist/Установщик_Классный_Страж.exe          ")
    print("==================================================")

if __name__ == "__main__":
    build()
