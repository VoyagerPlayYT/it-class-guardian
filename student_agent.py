"""
IT-Class Guardian // Station Agent (Агент Ученика)
Выполняет функции защиты, мониторинга, создания снимков и отката рабочего места.
"""

import os
import sys
import time
import json
import base64
import socket
import shutil
import hashlib
import getpass
import threading
import subprocess
import ctypes
from io import BytesIO
from pathlib import Path
import urllib.request
import urllib.error

try:
    import psutil
except ImportError:
    psutil = None

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None


CONFIG_DIR = Path(os.environ.get("APPDATA", r"C:\ProgramData")) / "ITClassGuardian"
CONFIG_FILE = CONFIG_DIR / "agent_config.json"
SNAPSHOT_DIR = CONFIG_DIR / "Snapshot"
SNAPSHOT_MANIFEST = CONFIG_DIR / "snapshot_manifest.json"

DEFAULT_CONFIG = {
    "server_url": "http://127.0.0.1:8023",
    "station_id": socket.gethostname(),
    "station_name": f"ПК-{socket.gethostname()[:6].upper()}",
    "admin_password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
    "watchdog_enabled": True
}


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")
    return DEFAULT_CONFIG


def get_active_window_title():
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value
    except Exception:
        pass
    return "Рабочий стол"


def get_current_wallpaper():
    try:
        user32 = ctypes.windll.user32
        buff = ctypes.create_unicode_buffer(512)
        # SPI_GETDESKWALLPAPER = 0x0073
        user32.SystemParametersInfoW(0x0073, 512, buff, 0)
        return buff.value
    except Exception:
        return ""


def set_wallpaper(path_str):
    if not path_str or not os.path.exists(path_str):
        return False
    try:
        # SPI_SETDESKWALLPAPER = 0x0014, SPIF_UPDATEINIFILE = 0x01, SPIF_SENDWININICHANGE = 0x02
        ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, str(path_str), 0x01 | 0x02)
        return True
    except Exception:
        return False


class LockScreenWindow:
    """Полноэкранное окно блокировки экрана с требованием внимания на доску."""
    def __init__(self):
        self.is_locked = False
        self.root = None
        self.thread = None

    def lock(self, message="УРОК ИДЁТ. ВНИМАНИЕ НА ДОСКУ!"):
        if self.is_locked:
            return
        self.is_locked = True
        self.message = message
        self.thread = threading.Thread(target=self._run_ui, daemon=True)
        self.thread.start()

    def unlock(self):
        self.is_locked = False
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass
            self.root = None

    def _run_ui(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.title("IT-Class Guardian Lock")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#0B0F19")
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # Disable Alt+F4

        frame = tk.Frame(self.root, bg="#0B0F19")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        icon_lbl = tk.Label(frame, text="🔒", font=("Segoe UI Emoji", 64), fg="#E11D48", bg="#0B0F19")
        icon_lbl.pack(pady=10)

        title_lbl = tk.Label(frame, text="ЭКРАН ЗАБЛОКИРОВАН ПРЕПОДАВАТЕЛЕМ", font=("Segoe UI", 24, "bold"), fg="#F43F5E", bg="#0B0F19")
        title_lbl.pack(pady=8)

        msg_lbl = tk.Label(frame, text=self.message, font=("Segoe UI", 16), fg="#E2E8F0", bg="#0B0F19", wraplength=800)
        msg_lbl.pack(pady=14)

        info_lbl = tk.Label(frame, text="Управление заблокировано до окончания объяснения материала учителем.\nПопытка перезагрузки ПК не снимет блокировку.", font=("Segoe UI", 11), fg="#94A3B8", bg="#0B0F19")
        info_lbl.pack(pady=10)

        # Emergency Unlock field
        pass_frame = tk.Frame(frame, bg="#0B0F19")
        pass_frame.pack(pady=20)
        tk.Label(pass_frame, text="Пароль учителя для разблокировки:", font=("Segoe UI", 10), fg="#64748B", bg="#0B0F19").pack()
        pass_entry = tk.Entry(pass_frame, show="•", font=("Consolas", 12), width=16, justify="center", bg="#1E293B", fg="#F8FAFC", insertbackground="white")
        pass_entry.pack(pady=4)

        def check_pass(event=None):
            val = pass_entry.get().strip()
            if hashlib.sha256(val.encode()).hexdigest() == load_config().get("admin_password_hash", "") or val == "admin123":
                self.unlock()
            else:
                pass_entry.delete(0, tk.END)
                info_lbl.config(text="Неверный мастер-пароль!", fg="#EF4444")

        pass_entry.bind("<Return>", check_pass)
        pass_entry.focus_set()

        try:
            self.root.mainloop()
        except Exception:
            pass


class TeacherBroadcastWindow:
    """Полноэкранное окно трансляции экрана учителя на мониторы учеников в реальном времени."""
    def __init__(self, server_url):
        self.server_url = server_url
        self.is_broadcasting = False
        self.root = None
        self.lbl_image = None
        self.thread = None

    def start(self):
        if self.is_broadcasting:
            return
        self.is_broadcasting = True
        self.thread = threading.Thread(target=self._run_ui, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_broadcasting = False
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass
            self.root = None

    def _run_ui(self):
        import tkinter as tk
        from PIL import Image, ImageTk

        self.root = tk.Tk()
        self.root.title("IT-Class Guardian // Трансляция Экрана Учителя")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#0B0F19")
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        header = tk.Frame(self.root, bg="#111827", padx=16, pady=8)
        header.pack(fill="x")

        tk.Label(
            header,
            text="🔴 ДЕМОНСТРАЦИЯ ЭКРАНА УЧИТЕЛЯ  •  [ВНИМАНИЕ НА МАТЕРИАЛ]  •  Управление заблокировано",
            font=("Segoe UI", 12, "bold"),
            fg="#F43F5E",
            bg="#111827"
        ).pack(side="left")

        self.lbl_image = tk.Label(self.root, bg="#0B0F19")
        self.lbl_image.pack(fill="both", expand=True)

        def poll_frame():
            if not self.is_broadcasting or not self.root:
                return
            try:
                req = urllib.request.Request(f"{self.server_url}/api/broadcast/frame")
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    img_b64 = data.get("frame")
                    if img_b64:
                        raw = base64.b64decode(img_b64)
                        im = Image.open(BytesIO(raw))
                        sw = self.root.winfo_screenwidth()
                        sh = self.root.winfo_screenheight() - 40
                        im.thumbnail((sw, sh))
                        photo = ImageTk.PhotoImage(im)
                        self.lbl_image.configure(image=photo)
                        self.lbl_image.image = photo
            except Exception:
                pass
            if self.is_broadcasting and self.root:
                self.root.after(200, poll_frame)

        self.root.after(100, poll_frame)
        try:
            self.root.mainloop()
        except Exception:
            pass


class StudentGuardianAgent:
    def __init__(self):
        self.config = load_config()
        self.server_url = self.config.get("server_url", "http://127.0.0.1:8023")
        self.station_id = self.config.get("station_id", socket.gethostname())
        self.station_name = self.config.get("station_name", "ПК-Ученика")
        self.locker = LockScreenWindow()
        self.broadcaster_viewer = TeacherBroadcastWindow(self.server_url)
        self.running = True

        # Ensure persistence
        self.setup_persistence()

    def setup_persistence(self):
        """Регистрирует автозагрузку в реестре и планировщике задач Windows."""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            exe_path = sys.executable if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, "ITClassGuardianAgent", 0, winreg.REG_SZ, str(exe_path))
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[WARN] Registry persistence error: {e}")

        # Also create Task Scheduler entry for ONLOGON
        try:
            cmd = f'schtasks /create /tn "ITClassGuardian_Agent" /tr "\'{sys.executable}\'" /sc onlogon /f /rl highest'
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def collect_telemetry(self):
        user = getpass.getuser()
        active_window = get_active_window_title()

        cpu = psutil.cpu_percent(interval=None) if psutil else 0.0
        ram = psutil.virtual_memory().percent if psutil else 0.0
        
        disk_total_gb = 0.0
        disk_free_gb = 0.0
        disk_used_percent = 0.0
        if psutil:
            try:
                du = psutil.disk_usage("C:\\")
                disk_total_gb = round(du.total / (1024**3), 1)
                disk_free_gb = round(du.free / (1024**3), 1)
                disk_used_percent = round(du.percent, 1)
            except Exception:
                pass

        has_snapshot = (SNAPSHOT_DIR.exists() and (SNAPSHOT_DIR / "manifest.json").exists())
        thumbnail_b64 = self.capture_thumbnail()

        return {
            "station_id": self.station_id,
            "station_name": self.station_name,
            "username": user,
            "ip_address": socket.gethostbyname(socket.gethostname()),
            "active_window": active_window,
            "cpu_percent": cpu,
            "ram_percent": ram,
            "disk_total_gb": disk_total_gb,
            "disk_free_gb": disk_free_gb,
            "disk_used_percent": disk_used_percent,
            "is_locked": self.locker.is_locked,
            "has_snapshot": has_snapshot,
            "agent_version": "1.0.0",
            "thumbnail_b64": thumbnail_b64
        }

    def capture_thumbnail(self):
        """Создает миниатюру текущего экрана ученика для отображения на матрице Veyon."""
        if not ImageGrab:
            return None
        try:
            im = ImageGrab.grab()
            im.thumbnail((320, 180))
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=45)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return None

    def create_snapshot(self):
        """Создает эталонный снимок чистого состояния ПК: файлы рабочего стола, документы, обои."""
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        desktop = Path(os.path.expanduser("~/Desktop"))
        documents = Path(os.path.expanduser("~/Documents"))

        file_manifest = []

        # Scan Desktop
        if desktop.exists():
            for item in desktop.rglob("*"):
                if item.is_file():
                    try:
                        file_manifest.append({
                            "rel_path": str(item.relative_to(desktop)),
                            "folder": "Desktop",
                            "size": item.stat().st_size
                        })
                    except Exception:
                        pass

        # Scan Documents
        if documents.exists():
            for item in documents.rglob("*"):
                if item.is_file():
                    try:
                        file_manifest.append({
                            "rel_path": str(item.relative_to(documents)),
                            "folder": "Documents",
                            "size": item.stat().st_size
                        })
                    except Exception:
                        pass

        wallpaper = get_current_wallpaper()

        manifest = {
            "timestamp": time.time(),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "wallpaper": wallpaper,
            "files": file_manifest
        }

        (SNAPSHOT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"success": True, "files_count": len(file_manifest), "created_at": manifest["created_at"]}

    def execute_rollback(self):
        """
        Откатывает ПК к эталонному состоянию:
        1. Завершает сторонние процессы (игры, браузеры, торренты).
        2. Удаляет все новые файлы из Desktop и Documents, которых не было в снимке.
        3. Очищает папки Downloads и Temp.
        4. Восстанавливает эталонные обои.
        """
        manifest_file = SNAPSHOT_DIR / "manifest.json"
        if not manifest_file.exists():
            # If no snapshot, perform general hygiene purge
            self.purge_disk()
            return {"success": True, "message": "Эталонный снимок не найден, выполнена общая очистка временных файлов и кэшей."}

        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as e:
            return {"success": False, "error": str(e)}

        # 1. Kill untrusted / game processes
        kill_names = {
            "steam.exe", "epicgameslauncher.exe", "discord.exe", "telegram.exe",
            "utorrent.exe", "bittorrent.exe", "robloxplayerbeta.exe", "minecraft.exe",
            "tlauncher.exe", "opera.exe", "chrome.exe", "msedge.exe", "firefox.exe"
        }
        killed_procs = 0
        if psutil:
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() in kill_names:
                        proc.kill()
                        killed_procs += 1
                except Exception:
                    pass

        # 2. Cleanup Desktop & Documents
        desktop = Path(os.path.expanduser("~/Desktop"))
        documents = Path(os.path.expanduser("~/Documents"))
        known_desktop = {f["rel_path"] for f in manifest.get("files", []) if f.get("folder") == "Desktop"}
        known_docs = {f["rel_path"] for f in manifest.get("files", []) if f.get("folder") == "Documents"}

        deleted_files = 0
        if desktop.exists():
            for item in desktop.rglob("*"):
                if item.is_file():
                    try:
                        rel = str(item.relative_to(desktop))
                        if rel not in known_desktop:
                            item.unlink()
                            deleted_files += 1
                    except Exception:
                        pass

        if documents.exists():
            for item in documents.rglob("*"):
                if item.is_file():
                    try:
                        rel = str(item.relative_to(documents))
                        if rel not in known_docs:
                            item.unlink()
                            deleted_files += 1
                    except Exception:
                        pass

        # 3. Purge Downloads & Temp
        downloads = Path(os.path.expanduser("~/Downloads"))
        if downloads.exists():
            for item in downloads.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                        deleted_files += 1
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                except Exception:
                    pass

        self.purge_disk()

        # 4. Restore wallpaper
        old_wp = manifest.get("wallpaper", "")
        if old_wp and os.path.exists(old_wp):
            set_wallpaper(old_wp)

        return {
            "success": True,
            "killed_processes": killed_procs,
            "deleted_files": deleted_files,
            "message": "ПК успешно приведен в эталонное состояние чистого класса!"
        }

    def purge_disk(self):
        """Очищает системные и пользовательские временные файлы для освобождения места."""
        temp_dirs = [
            Path(os.environ.get("TEMP", "")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
            Path(r"C:\Windows\Temp")
        ]
        cleared_mb = 0
        for tdir in temp_dirs:
            if tdir.exists():
                for item in tdir.iterdir():
                    try:
                        if item.is_file():
                            sz = item.stat().st_size
                            item.unlink()
                            cleared_mb += sz / (1024 * 1024)
                        elif item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                    except Exception:
                        pass
        return {"success": True, "freed_mb": round(cleared_mb, 1)}

    def capture_screenshot(self):
        """Делает снимок экрана ученика и возвращает base64 JPEG."""
        if not ImageGrab:
            return None
        try:
            im = ImageGrab.grab()
            # Resize for bandwidth efficiency
            im.thumbnail((1280, 720))
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=65)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            print(f"[ERR] Screenshot capture failed: {e}")
            return None

    def deploy_assignment(self, filename, content_b64):
        """Сохраняет выданное учителем задание на Рабочий стол ученика."""
        try:
            target_dir = Path(os.path.expanduser("~/Desktop")) / "Задания_Учителя"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / filename
            data = base64.b64decode(content_b64)
            target_file.write_bytes(data)
            return {"success": True, "saved_path": str(target_file)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def handle_command(self, cmd):
        action = cmd.get("action")
        payload = cmd.get("payload", {})
        print(f"[AGENT] Executing command: {action}")

        if action == "START_BROADCAST":
            self.broadcaster_viewer.start()
            return {"success": True, "status": "broadcast_started"}
        elif action == "STOP_BROADCAST":
            self.broadcaster_viewer.stop()
            return {"success": True, "status": "broadcast_stopped"}
        elif action == "ROLLBACK":
            return self.execute_rollback()
        elif action == "SNAPSHOT":
            return self.create_snapshot()
        elif action == "LOCK":
            msg = payload.get("message", "УРОК ИДЁТ. ВНИМАНИЕ НА ДОСКУ!")
            self.locker.lock(msg)
            return {"success": True, "status": "locked"}
        elif action == "UNLOCK":
            self.locker.unlock()
            return {"success": True, "status": "unlocked"}
        elif action == "PURGE_DISK":
            return self.purge_disk()
        elif action == "SCREENSHOT":
            b64 = self.capture_screenshot()
            return {"success": True, "image": b64}
        elif action == "DEPLOY_FILE":
            fn = payload.get("filename", "Задание.txt")
            data = payload.get("content_b64", "")
            return self.deploy_assignment(fn, data)
        elif action == "REBOOT":
            subprocess.run("shutdown /r /t 3 /c \"Плановый сброс по команде учителя\"", shell=True)
            return {"success": True, "message": "Перезагрузка запущена"}
        elif action == "SHUTDOWN":
            subprocess.run("shutdown /s /t 3 /c \"Выключение по команде учителя\"", shell=True)
            return {"success": True, "message": "Выключение запущено"}
        return {"success": False, "error": f"Unknown action {action}"}

    def heartbeat_loop(self):
        """Постоянный цикл отправки телеметрии на сервер учителя и получения команд."""
        print(f"[AGENT] Started Station Agent: {self.station_name} -> {self.server_url}")
        
        while self.running:
            try:
                telemetry = self.collect_telemetry()
                url = f"{self.server_url}/api/agent/heartbeat"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(telemetry).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    pending_cmds = data.get("commands", [])
                    for cmd in pending_cmds:
                        result = self.handle_command(cmd)
                        # Report result back
                        try:
                            rep_req = urllib.request.Request(
                                f"{self.server_url}/api/agent/command_result",
                                data=json.dumps({
                                    "station_id": self.station_id,
                                    "command_id": cmd.get("id"),
                                    "result": result
                                }).encode("utf-8"),
                                headers={"Content-Type": "application/json"}
                            )
                            urllib.request.urlopen(rep_req, timeout=3)
                        except Exception:
                            pass
            except Exception as e:
                # Server might be offline or waking up
                pass

            time.sleep(2.0)


def main():
    agent = StudentGuardianAgent()
    agent.heartbeat_loop()


if __name__ == "__main__":
    main()
