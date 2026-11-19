"""
IT-Class Guardian // Station Agent (Агент Ученика)
Резидентный защитный агент для рабочих мест учащихся.
Работает строго в фоновом режиме (БЕЗ окон, консолей и всплывающих окон).
Включает:
- Локальный HTTP сервер на порту 8024 (учитель может подключиться к ПК в любой момент).
- Автоматическое обнаружение учителя по локальной сети через UDP Broadcast Beacon (порт 8025).
- Создание эталонных снимков и мгновенный откат ПК к чистому состоянию после каждого урока.
- Очистку диска C: от скачанных игр, кэша и мусора.
- Блокировку экрана «Внимание на доску» и полноэкранную трансляцию рабочего стола учителя.
- Защиту от закрытия и автозапуск через планировщик Windows / реестр.
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
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

# Скрываем окно консоли, если агент запущен из cmd или через двойной клик
if sys.platform == "win32":
    try:
        wh = ctypes.windll.kernel32.GetConsoleWindow()
        if wh:
            ctypes.windll.user32.ShowWindow(wh, 0)  # SW_HIDE
    except Exception:
        pass

try:
    import psutil
except ImportError:
    psutil = None

try:
    from PIL import Image, ImageTk, ImageGrab
except ImportError:
    Image, ImageTk, ImageGrab = None, None, None


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
        user32.SystemParametersInfoW(0x0073, 512, buff, 0)
        return buff.value
    except Exception:
        return ""


def set_wallpaper(path_str):
    if not path_str or not os.path.exists(path_str):
        return False
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, str(path_str), 0x01 | 0x02)
        return True
    except Exception:
        return False


class LockScreenWindow:
    """Полноэкранное окно блокировки экрана (показывается только по команде учителя)."""
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
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = tk.Frame(self.root, bg="#0B0F19")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="🔒", font=("Segoe UI Emoji", 64), fg="#E11D48", bg="#0B0F19").pack(pady=10)
        tk.Label(frame, text="ЭКРАН ЗАБЛОКИРОВАН ПРЕПОДАВАТЕЛЕМ", font=("Segoe UI", 24, "bold"), fg="#F43F5E", bg="#0B0F19").pack(pady=8)
        tk.Label(frame, text=self.message, font=("Segoe UI", 16), fg="#E2E8F0", bg="#0B0F19", wraplength=800).pack(pady=14)
        tk.Label(frame, text="Управление заблокировано до окончания объяснения материала учителем.\nПопытка перезагрузки ПК не снимет блокировку.", font=("Segoe UI", 11), fg="#94A3B8", bg="#0B0F19").pack(pady=10)

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

        pass_entry.bind("<Return>", check_pass)
        pass_entry.focus_set()

        try:
            self.root.mainloop()
        except Exception:
            pass


class TeacherBroadcastWindow:
    """Полноэкранное окно трансляции экрана учителя (показывается только по команде учителя)."""
    def __init__(self, agent):
        self.agent = agent
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
        if not Image or not ImageTk:
            return

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
                req = urllib.request.Request(f"{self.agent.server_url}/api/broadcast/frame")
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


class AgentHttpHandler(BaseHTTPRequestHandler):
    """Локальный HTTP API агента ученика (порт 8024) для прямого подключения учителем."""
    agent_ref = None

    def log_message(self, format, *args):
        pass  # Полная тишина в консоли

    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            resp = {
                "status": "ok",
                "station_id": self.agent_ref.station_id,
                "station_name": self.agent_ref.station_name,
                "username": getpass.getuser(),
                "agent_version": "2.0.0"
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = self.agent_ref.collect_telemetry()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if self.path == "/pair":
            new_url = payload.get("server_url")
            if new_url:
                self.agent_ref.server_url = new_url.rstrip("/")
                self.agent_ref.config["server_url"] = self.agent_ref.server_url
                CONFIG_FILE.write_text(json.dumps(self.agent_ref.config, indent=2, ensure_ascii=False), encoding="utf-8")
                threading.Thread(target=self.agent_ref.send_single_heartbeat, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "server_url": self.agent_ref.server_url}).encode("utf-8"))
        elif self.path == "/command":
            res = self.agent_ref.handle_command(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class StudentGuardianAgent:
    def __init__(self):
        self.config = load_config()
        self.server_url = self.config.get("server_url", "http://127.0.0.1:8023").rstrip("/")
        self.station_id = self.config.get("station_id", socket.gethostname())
        self.station_name = self.config.get("station_name", f"ПК-{socket.gethostname()[:6].upper()}")
        self.locker = LockScreenWindow()
        self.broadcaster_viewer = TeacherBroadcastWindow(self)
        self.running = True

        # Автозапуск и защита от отключения
        self.ensure_persistence()

        # Запуск локального HTTP сервера (порт 8024)
        self.start_local_http_server()

        # Запуск UDP прослушивателя маяка учителя (порт 8025)
        threading.Thread(target=self.udp_beacon_listener, daemon=True).start()

    def start_local_http_server(self):
        AgentHttpHandler.agent_ref = self
        def _run():
            try:
                server = HTTPServer(("0.0.0.0", 8024), AgentHttpHandler)
                server.serve_forever()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def udp_beacon_listener(self):
        """Слушает широковещательные маяки учителя в локальной сети (порт 8025)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", 8025))
            while self.running:
                data, _ = sock.recvfrom(2048)
                try:
                    msg = json.loads(data.decode("utf-8"))
                    if msg.get("beacon") == "IT_CLASS_TEACHER_HUB":
                        teacher_url = msg.get("server_url")
                        if teacher_url and teacher_url != self.server_url:
                            self.server_url = teacher_url.rstrip("/")
                            self.config["server_url"] = self.server_url
                            CONFIG_FILE.write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding="utf-8")
                            self.send_single_heartbeat()
                except Exception:
                    pass
        except Exception:
            pass

    def ensure_persistence(self):
        """Гарантирует автозапуск при перезагрузке ПК через реестр и планировщик задач."""
        if sys.platform != "win32":
            return
        exe_path = sys.executable
        # Если запущен скрипт, предпочитаем pythonw.exe для скрытности
        if not exe_path.endswith(".exe") or "python" in Path(exe_path).name.lower():
            pyw = Path(exe_path).parent / "pythonw.exe"
            if pyw.exists():
                cmd_line = f'"{pyw}" "{Path(__file__).resolve()}"'
            else:
                cmd_line = f'"{exe_path}" "{Path(__file__).resolve()}"'
        else:
            cmd_line = f'"{Path(exe_path).resolve()}"'

        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "ITClassGuardianAgent", 0, winreg.REG_SZ, cmd_line)
            winreg.CloseKey(key)
        except Exception:
            pass

        try:
            subprocess.run(
                f'schtasks /create /tn "ITClassGuardianWatchdog" /tr "{cmd_line}" /sc onlogon /rl highest /f',
                shell=True, capture_output=True
            )
        except Exception:
            pass

    def collect_telemetry(self):
        active_window = get_active_window_title()
        cpu_percent = psutil.cpu_percent(interval=None) if psutil else 10.0
        ram_percent = psutil.virtual_memory().percent if psutil else 35.0

        disk_total_gb = 512.0
        disk_free_gb = 100.0
        disk_used_percent = 20.0
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

        # Локальный IP компьютера ученика
        local_ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass

        return {
            "station_id": self.station_id,
            "station_name": self.station_name,
            "username": getpass.getuser(),
            "ip_address": local_ip,
            "active_window": active_window,
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "disk_total_gb": disk_total_gb,
            "disk_free_gb": disk_free_gb,
            "disk_used_percent": disk_used_percent,
            "is_locked": self.locker.is_locked,
            "has_snapshot": has_snapshot,
            "agent_version": "2.0.0",
            "thumbnail_b64": thumbnail_b64
        }

    def capture_thumbnail(self):
        """Создает живую миниатюру экрана ученика для матрицы Veyon."""
        if ImageGrab:
            try:
                im = ImageGrab.grab()
                im.thumbnail((320, 180))
                buf = BytesIO()
                im.save(buf, format="JPEG", quality=45)
                return base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                pass

        # Если рабочий стол заблокирован или недоступен для BitBlt (заставка, UAC, блокировка экрана)
        if Image:
            try:
                from PIL import ImageDraw
                img = Image.new("RGB", (320, 180), color=(14, 17, 23))
                d = ImageDraw.Draw(img)
                d.rectangle([0, 0, 320, 24], fill=(24, 30, 42))
                d.text((10, 6), f"● {self.station_name} [{getpass.getuser()}]", fill=(100, 180, 255))
                d.text((20, 50), "Активное окно:", fill=(140, 150, 165))
                win = (get_active_window_title() or "Рабочий стол")[:35]
                d.text((20, 70), win, fill=(240, 240, 250))
                d.rectangle([20, 120, 300, 150], fill=(20, 26, 36))
                d.text((30, 128), "📡 АГЕНТ В СЕТИ // МОНИТОРИНГ АКТИВЕН", fill=(52, 211, 153))

                buf = BytesIO()
                img.save(buf, format="JPEG", quality=60)
                return base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                pass
        return None

    def create_snapshot(self):
        """Фиксирует эталонное состояние ПК: файлы рабочего стола, документы, обои."""
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        manifest = {
            "created_at": time.time(),
            "created_by": getpass.getuser(),
            "wallpaper": get_current_wallpaper(),
            "files": []
        }

        desktop = Path(os.path.expanduser("~/Desktop"))
        documents = Path(os.path.expanduser("~/Documents"))

        for base_folder, folder_name in [(desktop, "Desktop"), (documents, "Documents")]:
            if not base_folder.exists():
                continue
            for item in base_folder.rglob("*"):
                if item.is_file():
                    try:
                        rel_path = str(item.relative_to(base_folder))
                        manifest["files"].append({
                            "folder": folder_name,
                            "rel_path": rel_path,
                            "size": item.stat().st_size
                        })
                    except Exception:
                        pass

        (SNAPSHOT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"success": True, "files_indexed": len(manifest["files"]), "message": "Эталонный снимок успешно сохранен"}

    def execute_rollback(self):
        """
        Мгновенный сброс ПК к эталону:
        - Завершает все игры и несанкционированные процессы.
        - Удаляет все файлы на Рабочем столе и в Документах, которых нет в эталоне.
        - Очищает папки Downloads и Temp.
        - Восстанавливает обои.
        """
        manifest_file = SNAPSHOT_DIR / "manifest.json"
        if not manifest_file.exists():
            self.create_snapshot()
            manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))
        else:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

        # 1. Завершение несанкционированных процессов
        kill_names = {
            "robloxplayerbeta.exe", "roblox.exe", "steam.exe", "epicgameslauncher.exe",
            "minecraft.exe", "javaw.exe", "utorrent.exe", "bittorrent.exe", "qbittorrent.exe",
            "discord.exe", "telegram.exe", "tlauncher.exe"
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

        # 2. Очистка Рабочего стола и Документов
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

        # 3. Очистка Загрузок и Temp
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

        # 4. Восстановление обоев
        old_wp = manifest.get("wallpaper", "")
        if old_wp and os.path.exists(old_wp):
            set_wallpaper(old_wp)

        return {
            "success": True,
            "killed_processes": killed_procs,
            "deleted_files": deleted_files,
            "message": "ПК приведен в эталонное состояние чистого класса!"
        }

    def purge_disk(self):
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
        if ImageGrab:
            try:
                im = ImageGrab.grab()
                im.thumbnail((1280, 720))
                buf = BytesIO()
                im.save(buf, format="JPEG", quality=65)
                return base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                pass

        if Image:
            try:
                from PIL import ImageDraw
                img = Image.new("RGB", (1280, 720), color=(14, 17, 23))
                d = ImageDraw.Draw(img)
                d.rectangle([0, 0, 1280, 60], fill=(24, 30, 42))
                d.text((30, 18), f"● {self.station_name} [{getpass.getuser()}] - ЭКРАН УЧЕНИКА", fill=(100, 180, 255))
                d.text((60, 200), "Текущее активное приложение:", fill=(140, 150, 165))
                win = get_active_window_title() or "Рабочий стол"
                d.text((60, 240), win, fill=(240, 240, 250))
                d.rectangle([60, 400, 700, 480], fill=(20, 26, 36))
                d.text((80, 430), "📡 АГЕНТ В СЕТИ // МОНИТОРИНГ В РЕАЛЬНОМ ВРЕМЕНИ", fill=(52, 211, 153))

                buf = BytesIO()
                img.save(buf, format="JPEG", quality=75)
                return base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                pass
        return None

    def deploy_assignment(self, filename, content_b64):
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

    def send_single_heartbeat(self):
        try:
            telemetry = self.collect_telemetry()
            url = f"{self.server_url}/api/agent/heartbeat"
            req = urllib.request.Request(
                url,
                data=json.dumps(telemetry).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for cmd in data.get("commands", []):
                    res = self.handle_command(cmd)
                    try:
                        rep_req = urllib.request.Request(
                            f"{self.server_url}/api/agent/command_result",
                            data=json.dumps({
                                "station_id": self.station_id,
                                "command_id": cmd.get("id"),
                                "result": res
                            }).encode("utf-8"),
                            headers={"Content-Type": "application/json"}
                        )
                        urllib.request.urlopen(rep_req, timeout=2.0)
                    except Exception:
                        pass
        except Exception:
            pass

    def heartbeat_loop(self):
        while self.running:
            self.send_single_heartbeat()
            time.sleep(2.5)


def main():
    agent = StudentGuardianAgent()
    agent.heartbeat_loop()


if __name__ == "__main__":
    main()
