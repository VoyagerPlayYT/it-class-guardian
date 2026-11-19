"""
IT-Class Guardian // Teacher Server & Management Hub
Сервер управления компьютерным классом и рабочими станциями учеников (Порт 8023).
Включает:
- Монитор-стену экранов (Veyon-style) в реальном времени.
- Полноэкранную трансляцию экрана учителя на весь класс.
- Ручное и автоматическое подключение ПК учеников по сети (LAN Scan & Auto-Discovery).
- Защиту от переполнения диска C: и откат к эталону после уроков.
- Полное отсутствие заглушек: работают только реальные подключенные ПК.
"""

import os
import sys
import time
import json
import socket
import sqlite3
import base64
import asyncio
import threading
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

try:
    from PIL import Image, ImageGrab
except ImportError:
    Image, ImageGrab = None, None


app = FastAPI(title="IT-Class Guardian Server", version="2.0.0")

BASE_DIR = Path(os.environ.get("IT_CLASS_BUNDLE_DIR", Path(__file__).resolve().parent))
STATIC_DIR = BASE_DIR / "static"
DB_PATH = Path(os.environ.get("LOCALAPPDATA", str(BASE_DIR))) / "ITClassGuardian" / "guardian.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_lan_ip() -> str:
    """Определяет реальный IP-адрес компьютера учителя в локальной сети."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class TeacherScreenBroadcaster:
    """Фоновый захват экрана учителя для трансляции на мониторы всех учеников."""
    def __init__(self):
        self.is_broadcasting = False
        self.latest_frame_b64 = None
        self.thread = None

    def start(self):
        if self.is_broadcasting:
            return
        self.is_broadcasting = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_broadcasting = False

    def push_frame(self, frame_b64: str):
        self.latest_frame_b64 = frame_b64

    def _capture_loop(self):
        while self.is_broadcasting:
            if ImageGrab:
                try:
                    im = ImageGrab.grab()
                    im.thumbnail((1280, 720))
                    buf = BytesIO()
                    im.save(buf, format="JPEG", quality=60)
                    self.latest_frame_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                except Exception:
                    pass
            time.sleep(0.2)  # ~5 FPS


broadcaster = TeacherScreenBroadcaster()


def udp_beacon_loop():
    """Широковещательный маяк (UDP broadcast на 8025): агенты на ПК учеников находят учителя автоматически."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except Exception:
        pass
    while True:
        try:
            lan_ip = get_lan_ip()
            payload = json.dumps({
                "beacon": "IT_CLASS_TEACHER_HUB",
                "server_url": f"http://{lan_ip}:8023",
                "teacher_ip": lan_ip,
                "port": 8023
            }).encode("utf-8")
            sock.sendto(payload, ("255.255.255.255", 8025))
        except Exception:
            pass
        time.sleep(3.0)


threading.Thread(target=udp_beacon_loop, daemon=True).start()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stations (
        station_id TEXT PRIMARY KEY,
        station_name TEXT NOT NULL,
        username TEXT,
        ip_address TEXT,
        active_window TEXT,
        cpu_percent REAL,
        ram_percent REAL,
        disk_total_gb REAL,
        disk_free_gb REAL,
        disk_used_percent REAL,
        is_locked INTEGER DEFAULT 0,
        has_snapshot INTEGER DEFAULT 0,
        last_seen REAL,
        latest_screenshot TEXT,
        latest_thumbnail TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id TEXT NOT NULL,
        action TEXT NOT NULL,
        payload TEXT,
        status TEXT DEFAULT 'PENDING',
        result TEXT,
        created_at REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        station_id TEXT,
        station_name TEXT,
        details TEXT,
        created_at REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        filename TEXT NOT NULL,
        content_b64 TEXT NOT NULL,
        created_at REAL
    )
    """)

    # Полное удаление любых устаревших демо-заглушек
    cur.execute("DELETE FROM stations WHERE station_id LIKE 'STATION-%'")
    cur.execute("DELETE FROM audit_logs WHERE details LIKE '%демо%' OR details LIKE '%Инициализация%'")

    conn.commit()
    conn.close()


init_db()


class HeartbeatPayload(BaseModel):
    station_id: str
    station_name: str
    username: str
    ip_address: str
    active_window: str
    cpu_percent: float
    ram_percent: float
    disk_total_gb: float
    disk_free_gb: float
    disk_used_percent: float
    is_locked: bool
    has_snapshot: bool
    agent_version: str
    thumbnail_b64: Optional[str] = None


class CommandRequest(BaseModel):
    action: str
    payload: Optional[Dict[str, Any]] = None


class CommandResultPayload(BaseModel):
    station_id: str
    command_id: Optional[int] = None
    result: Dict[str, Any]


class FramePushPayload(BaseModel):
    frame_b64: str


class StationConnectRequest(BaseModel):
    ip: str
    port: int = 8024
    station_name: Optional[str] = None


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_conns = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_conns.append(connection)
        for d in dead_conns:
            self.disconnect(d)


manager = ConnectionManager()
test_agent_proc = None


@app.get("/")
def get_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>IT-Class Guardian Server is Running</h1>")


@app.get("/api/network/info")
def get_network_info():
    """Возвращает сетевые координаты сервера учителя для отображения в интерфейсе."""
    lan_ip = get_lan_ip()
    return {
        "teacher_ip": lan_ip,
        "port": 8023,
        "server_url": f"http://{lan_ip}:8023"
    }


@app.post("/api/stations/connect")
def connect_student_station(req: StationConnectRequest):
    """
    Учитель вручную подключает компьютер ученика по IP-адресу.
    Сервер учителя отправляет запрос на ПК ученика (порт 8024), привязывает его и запрашивает телеметрию.
    """
    ip = req.ip.strip()
    port = req.port or 8024
    lan_ip = get_lan_ip()
    teacher_server_url = f"http://{lan_ip}:8023"

    import urllib.request
    try:
        # 1. Привязка агента к серверу учителя
        pair_req = urllib.request.Request(
            f"http://{ip}:{port}/pair",
            data=json.dumps({"server_url": teacher_server_url}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(pair_req, timeout=3.0) as resp:
            pair_resp = json.loads(resp.read().decode("utf-8"))

        # 2. Получение первичной телеметрии и снимка экрана
        status_req = urllib.request.Request(f"http://{ip}:{port}/status")
        with urllib.request.urlopen(status_req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        station_id = data.get("station_id", f"PC_{ip.replace('.', '_')}")
        station_name = req.station_name or data.get("station_name", f"ПК-{ip}")
        now = time.time()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO stations (station_id, station_name, username, ip_address, active_window, cpu_percent, ram_percent, disk_total_gb, disk_free_gb, disk_used_percent, is_locked, has_snapshot, last_seen, latest_thumbnail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(station_id) DO UPDATE SET
            station_name = excluded.station_name,
            username = excluded.username,
            ip_address = excluded.ip_address,
            active_window = excluded.active_window,
            cpu_percent = excluded.cpu_percent,
            ram_percent = excluded.ram_percent,
            disk_total_gb = excluded.disk_total_gb,
            disk_free_gb = excluded.disk_free_gb,
            disk_used_percent = excluded.disk_used_percent,
            is_locked = excluded.is_locked,
            has_snapshot = excluded.has_snapshot,
            last_seen = excluded.last_seen,
            latest_thumbnail = COALESCE(excluded.latest_thumbnail, stations.latest_thumbnail)
        """, (
            station_id, station_name, data.get("username", "user"), ip,
            data.get("active_window", "Рабочий стол"),
            data.get("cpu_percent", 0.0), data.get("ram_percent", 0.0),
            data.get("disk_total_gb", 512.0), data.get("disk_free_gb", 100.0),
            data.get("disk_used_percent", 20.0),
            1 if data.get("is_locked") else 0,
            1 if data.get("has_snapshot") else 0,
            now,
            data.get("thumbnail_b64")
        ))

        cur.execute("""
        INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
        VALUES ('CONNECT', ?, ?, ?, ?)
        """, (station_id, station_name, f"Учитель успешно подключил станцию ученика {station_name} ({ip}:{port})", now))

        conn.commit()
        conn.close()

        return {"success": True, "station_id": station_id, "station_name": station_name, "ip": ip}
    except Exception as e:
        return {
            "success": False,
            "error": f"Не удалось подключиться к {ip}:{port} ({e}). Убедитесь, что на ПК ученика запущен Агент_Ученика.exe и оба ПК находятся в одной сети."
        }


@app.post("/api/network/scan")
def scan_network_for_students():
    """
    Быстрое многопоточное сканирование подсети класса на наличие запущенных агентов учеников (порт 8024).
    """
    lan_ip = get_lan_ip()
    ip_parts = lan_ip.split(".")
    candidates = []
    if len(ip_parts) == 4 and lan_ip != "127.0.0.1":
        prefix = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}."
        candidates = [f"{prefix}{i}" for i in range(1, 255)]
    candidates.append("127.0.0.1")

    def probe(ip):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.18)
        try:
            code = s.connect_ex((ip, 8024))
            s.close()
            if code == 0:
                return ip
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=75) as ex:
        active_ips = list(filter(None, ex.map(probe, candidates)))

    found_list = []
    teacher_server_url = f"http://{lan_ip}:8023"
    import urllib.request
    for ip in active_ips:
        try:
            pair_req = urllib.request.Request(
                f"http://{ip}:8024/pair",
                data=json.dumps({"server_url": teacher_server_url}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(pair_req, timeout=1.5)

            status_req = urllib.request.Request(f"http://{ip}:8024/status")
            with urllib.request.urlopen(status_req, timeout=1.5) as r:
                st = json.loads(r.read().decode("utf-8"))
                st["ip"] = ip
                found_list.append(st)
        except Exception:
            pass

    return {
        "success": True,
        "scanned_ips": len(candidates),
        "found_count": len(found_list),
        "found": found_list
    }


@app.delete("/api/stations/{station_id}")
def delete_station(station_id: str):
    """Удаляет рабочее место из списка (например, если ПК отключен или перенесен)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM stations WHERE station_id = ?", (station_id,))
    cur.execute("""
    INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
    VALUES ('DISCONNECT', ?, ?, 'Рабочее место удалено учителем', ?)
    """, (station_id, station_id, time.time()))
    conn.commit()
    conn.close()
    return {"success": True, "station_id": station_id}


@app.post("/api/test_agent/start")
def start_test_agent():
    """Запускает локальный скрытый агент ученика в фоне (без окна) для мгновенной проверки."""
    global test_agent_proc
    agent_script = BASE_DIR / "student_agent.py"
    py_exe = sys.executable
    if sys.platform == "win32":
        pyw_candidate = Path(py_exe).parent / "pythonw.exe"
        if pyw_candidate.exists():
            py_exe = str(pyw_candidate)

    creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    test_agent_proc = subprocess.Popen(
        [py_exe, str(agent_script)],
        cwd=str(BASE_DIR),
        creationflags=creation_flags
    )
    time.sleep(1.0)
    return {"success": True, "message": "Скрытый агент ученика успешно запущен в фоне (без окна)"}


@app.post("/api/test_agent/stop")
def stop_test_agent():
    """Останавливает локальный тестовый агент ученика."""
    global test_agent_proc
    if test_agent_proc:
        try:
            test_agent_proc.terminate()
        except Exception:
            pass
        test_agent_proc = None
    if sys.platform == "win32":
        subprocess.run('wmic process where "commandline like \'%student_agent.py%\'" call terminate', shell=True, capture_output=True)
        subprocess.run('taskkill /f /im Агент_Ученика.exe >nul 2>&1', shell=True, capture_output=True)
    return {"success": True, "message": "Агент ученика остановлен"}


@app.post("/api/agent/heartbeat")
def handle_heartbeat(data: HeartbeatPayload):
    """Принимает регулярный сигнал и живой скриншот экрана от агента ученика."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.time()

    cur.execute("""
    INSERT INTO stations (station_id, station_name, username, ip_address, active_window, cpu_percent, ram_percent, disk_total_gb, disk_free_gb, disk_used_percent, is_locked, has_snapshot, last_seen, latest_thumbnail)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(station_id) DO UPDATE SET
        station_name = excluded.station_name,
        username = excluded.username,
        ip_address = excluded.ip_address,
        active_window = excluded.active_window,
        cpu_percent = excluded.cpu_percent,
        ram_percent = excluded.ram_percent,
        disk_total_gb = excluded.disk_total_gb,
        disk_free_gb = excluded.disk_free_gb,
        disk_used_percent = excluded.disk_used_percent,
        is_locked = excluded.is_locked,
        has_snapshot = excluded.has_snapshot,
        last_seen = excluded.last_seen,
        latest_thumbnail = COALESCE(excluded.latest_thumbnail, stations.latest_thumbnail)
    """, (
        data.station_id, data.station_name, data.username, data.ip_address, data.active_window,
        data.cpu_percent, data.ram_percent, data.disk_total_gb, data.disk_free_gb,
        data.disk_used_percent, 1 if data.is_locked else 0, 1 if data.has_snapshot else 0, now,
        data.thumbnail_b64
    ))

    # Извлечение ожидающих команд для этого ПК
    cur.execute("""
    SELECT id, action, payload FROM commands
    WHERE (station_id = ? OR station_id = 'ALL') AND status = 'PENDING'
    ORDER BY id ASC
    """, (data.station_id,))
    rows = cur.fetchall()

    pending_cmds = []
    cmd_ids_to_mark = []
    for cid, action, payload_str in rows:
        payload = json.loads(payload_str) if payload_str else {}
        pending_cmds.append({"id": cid, "action": action, "payload": payload})
        cmd_ids_to_mark.append(cid)

    for cid in cmd_ids_to_mark:
        cur.execute("UPDATE commands SET status = 'SENT' WHERE id = ?", (cid,))

    conn.commit()
    conn.close()

    return {"status": "ok", "commands": pending_cmds, "is_broadcasting": broadcaster.is_broadcasting}


@app.post("/api/agent/command_result")
def handle_command_result(data: CommandResultPayload):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.time()

    if data.command_id:
        cur.execute("""
        UPDATE commands SET status = 'EXECUTED', result = ? WHERE id = ?
        """, (json.dumps(data.result, ensure_ascii=False), data.command_id))

    if "image" in data.result and data.result["image"]:
        cur.execute("UPDATE stations SET latest_screenshot = ? WHERE station_id = ?", (data.result["image"], data.station_id))

    action_info = data.result.get("message", "Команда выполнена успешно")
    cur.execute("""
    INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, ("CMD_RESULT", data.station_id, data.station_id, action_info, now))

    conn.commit()
    conn.close()
    return {"status": "recorded"}


@app.get("/api/stations")
def get_stations():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM stations ORDER BY station_name ASC")
    rows = cur.fetchall()
    conn.close()

    now = time.time()
    stations_list = []
    for r in rows:
        item = dict(r)
        item["is_online"] = (now - item["last_seen"]) < 15.0
        item["disk_alert"] = item["disk_free_gb"] < 25.0
        item["game_detected"] = any(w in item["active_window"].lower() for w in ["roblox", "steam", "minecraft", "torrent", "discord", "игры"])
        stations_list.append(item)

    return {
        "stations": stations_list,
        "total": len(stations_list),
        "timestamp": now,
        "broadcast_active": broadcaster.is_broadcasting,
        "teacher_ip": get_lan_ip()
    }


@app.post("/api/broadcast")
def broadcast_command(req: CommandRequest):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.time()

    payload_json = json.dumps(req.payload or {}, ensure_ascii=False)
    cur.execute("""
    INSERT INTO commands (station_id, action, payload, status, created_at)
    VALUES ('ALL', ?, ?, 'PENDING', ?)
    """, (req.action, payload_json, now))

    cur.execute("""
    INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
    VALUES ('BROADCAST', 'ALL', 'Весь класс', ?, ?)
    """, (f"Массовая операция: {req.action}", now))

    conn.commit()
    conn.close()
    return {"success": True, "action": req.action, "target": "ALL"}


@app.post("/api/broadcast/start_screen")
def start_teacher_broadcast():
    broadcaster.start()
    broadcast_command(CommandRequest(action="START_BROADCAST"))
    return {"success": True, "broadcasting": True}


@app.post("/api/broadcast/stop_screen")
def stop_teacher_broadcast():
    broadcaster.stop()
    broadcast_command(CommandRequest(action="STOP_BROADCAST"))
    return {"success": True, "broadcasting": False}


@app.get("/api/broadcast/frame")
def get_broadcast_frame():
    return {"broadcasting": broadcaster.is_broadcasting, "frame": broadcaster.latest_frame_b64}


@app.post("/api/broadcast/push_frame")
def push_broadcast_frame(data: FramePushPayload):
    broadcaster.push_frame(data.frame_b64)
    return {"status": "ok"}


@app.get("/api/broadcast/status")
def get_broadcast_status():
    return {"broadcasting": broadcaster.is_broadcasting}


@app.post("/api/stations/{station_id}/command")
def send_station_command(station_id: str, req: CommandRequest):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.time()

    payload_json = json.dumps(req.payload or {}, ensure_ascii=False)
    cur.execute("""
    INSERT INTO commands (station_id, action, payload, status, created_at)
    VALUES (?, ?, ?, 'PENDING', ?)
    """, (station_id, req.action, payload_json, now))

    cur.execute("""
    INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
    VALUES ('COMMAND', ?, ?, ?, ?)
    """, (station_id, station_id, f"Команда: {req.action}", now))

    conn.commit()
    conn.close()
    return {"success": True, "station_id": station_id, "action": req.action}


@app.get("/api/stations/{station_id}/screenshot")
def get_station_screenshot(station_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT latest_screenshot, station_name FROM stations WHERE station_id = ?", (station_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        send_station_command(station_id, CommandRequest(action="SCREENSHOT"))
        return {"screenshot": None, "pending": True}
    return {"screenshot": row[0], "station_name": row[1]}


@app.get("/api/logs")
def get_logs(limit: int = 30):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


@app.post("/api/assignments/deploy")
async def deploy_assignment(title: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    b64_str = base64.b64encode(content).decode("ascii")
    now = time.time()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO assignments (title, filename, content_b64, created_at)
    VALUES (?, ?, ?, ?)
    """, (title, file.filename, b64_str, now))

    payload = json.dumps({"filename": file.filename, "content_b64": b64_str}, ensure_ascii=False)
    cur.execute("""
    INSERT INTO commands (station_id, action, payload, status, created_at)
    VALUES ('ALL', 'DEPLOY_FILE', ?, 'PENDING', ?)
    """, (payload, now))

    cur.execute("""
    INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
    VALUES ('ASSIGNMENT', 'ALL', 'Весь класс', ?, ?)
    """, (f"Раздача задания: {title} ({file.filename})", now))

    conn.commit()
    conn.close()
    return {"success": True, "filename": file.filename}


@app.websocket("/ws/classroom")
async def websocket_classroom(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT station_id, station_name, username, ip_address, active_window, cpu_percent, ram_percent, disk_free_gb, disk_used_percent, is_locked, has_snapshot, last_seen, latest_thumbnail FROM stations ORDER BY station_name ASC")
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            now = time.time()
            for r in rows:
                r["is_online"] = (now - r["last_seen"]) < 15.0
                r["disk_alert"] = r["disk_free_gb"] < 25.0
                r["game_detected"] = any(w in r["active_window"].lower() for w in ["roblox", "steam", "minecraft", "torrent", "discord", "игры"])

            await websocket.send_json({
                "type": "STATIONS_UPDATE",
                "stations": rows,
                "timestamp": now,
                "broadcast_active": broadcaster.is_broadcasting,
                "teacher_ip": get_lan_ip()
            })
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        pass
