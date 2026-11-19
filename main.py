"""
IT-Class Guardian // Teacher Server & Management Hub
Сервер управления компьютерным классом и рабочими местами учеников (Порт 8023)
"""

import os
import sys
import time
import json
import sqlite3
import base64
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="IT-Class Guardian Server", version="1.0.0")

BASE_DIR = Path(os.environ.get("IT_CLASS_BUNDLE_DIR", Path(__file__).resolve().parent))
STATIC_DIR = BASE_DIR / "static"
DB_PATH = Path(os.environ.get("LOCALAPPDATA", str(BASE_DIR))) / "ITClassGuardian" / "guardian.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
        latest_screenshot TEXT
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

    # Seed demonstration classroom stations if empty
    cur.execute("SELECT COUNT(*) FROM stations")
    if cur.fetchone()[0] == 0:
        demo_stations = [
            ("STATION-01", "ПК-01 (Иванов А.)", "alex_i", "192.168.1.101", "Visual Studio Code - main.py", 14.5, 38.2, 512.0, 340.5, 33.5, 0, 1),
            ("STATION-02", "ПК-02 (Смирнов Д.)", "dmitry_s", "192.168.1.102", "Roblox Player Beta (Внимание!)", 78.4, 82.0, 512.0, 18.2, 96.4, 0, 0),
            ("STATION-03", "ПК-03 (Кузнецова М.)", "maria_k", "192.168.1.103", "Яндекс Браузер - Реферат по информатике", 22.0, 45.1, 512.0, 410.0, 19.9, 0, 1),
            ("STATION-04", "ПК-04 (Попов М.)", "maksim_p", "192.168.1.104", "Steam - Загрузка обновления", 64.0, 71.3, 512.0, 4.8, 99.1, 0, 0),
            ("STATION-05", "ПК-05 (Васильев К.)", "kirill_v", "192.168.1.105", "Python 3.13 IDLE - turtle_draw.py", 18.2, 34.0, 512.0, 395.0, 22.8, 0, 1),
            ("STATION-06", "ПК-06 (Петрова Е.)", "elena_p", "192.168.1.106", "Блокнот - Конспект урока", 5.0, 28.6, 512.0, 430.0, 16.0, 0, 1),
            ("STATION-07", "ПК-07 (Новиков С.)", "sergey_n", "192.168.1.107", "Torrent Клиент (Забивает канал)", 85.0, 89.4, 512.0, 12.0, 97.6, 0, 0),
            ("STATION-08", "ПК-08 (Федоров И.)", "igor_f", "192.168.1.108", "PyCharm Community 2026", 31.0, 58.0, 512.0, 290.0, 43.3, 0, 1),
            ("STATION-09", "ПК-09 (Морозов В.)", "vlad_m", "192.168.1.109", "Discord - Голосовой канал", 28.0, 62.0, 512.0, 320.0, 37.5, 0, 0),
            ("STATION-10", "ПК-10 (Волкова А.)", "anna_v", "192.168.1.110", "Paint - Схема алгоритма", 8.0, 30.5, 512.0, 415.0, 18.9, 0, 1),
            ("STATION-11", "ПК-11 (Алексеев Д.)", "danil_a", "192.168.1.111", "Telegram Desktop", 19.0, 48.0, 512.0, 370.0, 27.7, 0, 0),
            ("STATION-12", "ПК-12 (Лебедев Н.)", "nikita_l", "192.168.1.112", "Командная строка cmd.exe", 12.0, 32.0, 512.0, 385.0, 24.8, 0, 1),
        ]
        now = time.time()
        for s_id, s_name, user, ip, win, cpu, ram, total, free, used, locked, snap in demo_stations:
            cur.execute("""
            INSERT INTO stations (station_id, station_name, username, ip_address, active_window, cpu_percent, ram_percent, disk_total_gb, disk_free_gb, disk_used_percent, is_locked, has_snapshot, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (s_id, s_name, user, ip, win, cpu, ram, total, free, used, locked, snap, now))

        cur.execute("""
        INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, ("SYS_INIT", "SERVER", "Сервер Учителя", "Инициализация журнала аудита и реестра компьютеров класса.", now))

    conn.commit()
    conn.close()


init_db()


# Models
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


class CommandRequest(BaseModel):
    action: str
    payload: Optional[Dict[str, Any]] = None


class CommandResultPayload(BaseModel):
    station_id: str
    command_id: Optional[int] = None
    result: Dict[str, Any]


# WebSocket Connection Manager
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


@app.get("/")
def get_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>IT-Class Guardian Server is Running</h1>")


@app.post("/api/agent/heartbeat")
def handle_heartbeat(data: HeartbeatPayload):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.time()

    cur.execute("""
    INSERT INTO stations (station_id, station_name, username, ip_address, active_window, cpu_percent, ram_percent, disk_total_gb, disk_free_gb, disk_used_percent, is_locked, has_snapshot, last_seen)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        last_seen = excluded.last_seen
    """, (
        data.station_id, data.station_name, data.username, data.ip_address, data.active_window,
        data.cpu_percent, data.ram_percent, data.disk_total_gb, data.disk_free_gb,
        data.disk_used_percent, 1 if data.is_locked else 0, 1 if data.has_snapshot else 0, now
    ))

    # Retrieve pending commands for this station or ALL
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

    # Mark as EXECUTING so it won't be sent multiple times
    for cid in cmd_ids_to_mark:
        cur.execute("UPDATE commands SET status = 'SENT' WHERE id = ?", (cid,))

    conn.commit()
    conn.close()

    return {"status": "ok", "commands": pending_cmds}


@app.post("/api/agent/command_result")
def handle_command_result(data: CommandResultPayload):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.time()

    if data.command_id:
        cur.execute("""
        UPDATE commands SET status = 'EXECUTED', result = ? WHERE id = ?
        """, (json.dumps(data.result, ensure_ascii=False), data.command_id))

    # If result contains screenshot, save it to station
    if "image" in data.result and data.result["image"]:
        cur.execute("UPDATE stations SET latest_screenshot = ? WHERE station_id = ?", (data.result["image"], data.station_id))

    # Add audit log
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
        # Online threshold 15 seconds
        item["is_online"] = (now - item["last_seen"]) < 15.0
        # Alert if disk is low (< 25 GB free) or CPU is pinned
        item["disk_alert"] = item["disk_free_gb"] < 25.0
        item["game_detected"] = any(w in item["active_window"].lower() for w in ["roblox", "steam", "minecraft", "torrent", "discord", "игры"])
        stations_list.append(item)

    return {"stations": stations_list, "total": len(stations_list), "timestamp": now}


@app.post("/api/broadcast")
def broadcast_command(req: CommandRequest):
    """Отправляет команду всем ПК в классе."""
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
    """, (f"Массовая команда: {req.action}", now))

    conn.commit()
    conn.close()
    return {"success": True, "action": req.action, "target": "ALL"}


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
    VALUES ('TARGET_CMD', ?, ?, ?, ?)
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
        # Trigger capture
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
    """Учитель загружает файл практической работы или теста, и сервер раздает его всем ученикам."""
    content = await file.read()
    b64_str = base64.b64encode(content).decode("ascii")
    now = time.time()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO assignments (title, filename, content_b64, created_at)
    VALUES (?, ?, ?, ?)
    """, (title, file.filename, b64_str, now))

    # Broadcast DEPLOY_FILE command to all stations
    payload = json.dumps({"filename": file.filename, "content_b64": b64_str}, ensure_ascii=False)
    cur.execute("""
    INSERT INTO commands (station_id, action, payload, status, created_at)
    VALUES ('ALL', 'DEPLOY_FILE', ?, 'PENDING', ?)
    """, (payload, now))

    cur.execute("""
    INSERT INTO audit_logs (event_type, station_id, station_name, details, created_at)
    VALUES ('ASSIGNMENT', 'ALL', 'Весь класс', ?, ?)
    """, (f"Раздача задания «{title}» (файл: {file.filename}, размер: {len(content)} байт)", now))

    conn.commit()
    conn.close()
    return {"success": True, "filename": file.filename, "size_bytes": len(content)}


@app.websocket("/ws/classroom")
async def websocket_classroom(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send live stations update every 2 seconds
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT station_id, station_name, username, ip_address, active_window, cpu_percent, ram_percent, disk_free_gb, disk_used_percent, is_locked, has_snapshot, last_seen FROM stations ORDER BY station_name ASC")
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
                "timestamp": now
            })
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8023, reload=False)
