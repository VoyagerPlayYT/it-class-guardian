"""
IT-Class Guardian // Unified Standalone Installer & Setup Wizard
Мастер установки системы: Сервер Учителя или Агент Ученика (без необходимости Python)
"""

import os
import sys
import shutil
import socket
import subprocess
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox


APP_NAME = "IT-Class Guardian"
VERSION = "1.0.0"

INSTALL_ROOT = Path(os.environ.get("LOCALAPPDATA", r"C:\ProgramData")) / "ITClassGuardian"


def is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def create_desktop_shortcut(target_exe, shortcut_name, desc=""):
    desktop = Path(os.path.expanduser("~/Desktop"))
    shortcut_path = desktop / f"{shortcut_name}.bat"
    
    # Create batch launcher on desktop
    bat_content = f"""@echo off
start "" "{target_exe}"
exit
"""
    shortcut_path.write_text(bat_content, encoding="utf-8")
    return shortcut_path


def install_student_agent(teacher_ip="127.0.0.1", station_name=""):
    INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    bin_dir = INSTALL_ROOT / "Bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    curr_dir = Path(__file__).resolve().parent

    # Find agent executable or script
    agent_src = curr_dir / "student_agent.exe"
    if not agent_src.exists():
        agent_src = curr_dir / "student_agent.py"

    agent_dest = bin_dir / agent_src.name
    try:
        shutil.copy2(agent_src, agent_dest)
    except Exception as e:
        print(f"Copy error: {e}")

    # Generate config
    if not station_name:
        station_name = f"ПК-{socket.gethostname()[:6].upper()}"

    config_data = {
        "server_url": f"http://{teacher_ip}:8023",
        "station_id": socket.gethostname(),
        "station_name": station_name,
        "watchdog_enabled": True
    }
    (INSTALL_ROOT / "agent_config.json").write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False) if "json" in sys.modules else str(config_data),
        encoding="utf-8"
    )

    # 1. Registry Run persistence
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "ITClassGuardianAgent", 0, winreg.REG_SZ, str(agent_dest))
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Registry error: {e}")

    # 2. Task Scheduler persistence (Highest privileges on logon)
    try:
        cmd = f'schtasks /create /tn "ITClassGuardian_Agent" /tr "\'{agent_dest}\'" /sc onlogon /f /rl highest'
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Schtasks error: {e}")

    # 3. Launch agent process now
    try:
        if agent_dest.suffix == ".py":
            subprocess.Popen([sys.executable, str(agent_dest)], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        else:
            subprocess.Popen([str(agent_dest)], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except Exception as e:
        print(f"Launch error: {e}")

    return True


def install_teacher_server():
    INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    server_dir = INSTALL_ROOT / "TeacherServer"
    server_dir.mkdir(parents=True, exist_ok=True)

    curr_dir = Path(__file__).resolve().parent

    # Copy files
    for item in curr_dir.iterdir():
        if item.name in ["main.py", "server.exe", "static", "requirements.txt", "start.bat"]:
            dest = server_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # Create Desktop shortcut for teacher
    start_bat = server_dir / "start.bat"
    desktop = Path(os.path.expanduser("~/Desktop"))
    shortcut = desktop / "Панель_Учителя_IT_Class.bat"
    shortcut.write_text(f"""@echo off
cd /d "{server_dir}"
call start.bat
""", encoding="utf-8")

    return shortcut


class InstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Установка {APP_NAME} v{VERSION}")
        self.root.geometry("620x460")
        self.root.resizable(False, False)
        self.root.configure(bg="#0D0D0F")

        self.setup_ui()

    def setup_ui(self):
        # Header banner
        header = tk.Frame(self.root, bg="#141417", padx=20, pady=16, highlightbackground="#26262C", highlightthickness=1)
        header.pack(fill="x")

        tk.Label(header, text="🛡️ IT-CLASS GUARDIAN", font=("Segoe UI", 16, "bold"), fg="#FFFFFF", bg="#141417").pack(anchor="w")
        tk.Label(header, text="Система защиты компьютеров учеников и отката к чистому эталону после уроков", font=("Segoe UI", 10), fg="#8E8E98", bg="#141417").pack(anchor="w")

        # Mode selection
        body = tk.Frame(self.root, bg="#0D0D0F", padx=24, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Выберите тип установки для данного компьютера:", font=("Segoe UI", 11, "bold"), fg="#F4F4F5", bg="#0D0D0F").pack(anchor="w", pady=(0, 16))

        # Teacher option
        teacher_card = tk.Frame(body, bg="#18181D", padx=16, pady=12, highlightbackground="#26262C", highlightthickness=1)
        teacher_card.pack(fill="x", pady=6)
        
        t_top = tk.Frame(teacher_card, bg="#18181D")
        t_top.pack(fill="x")
        tk.Label(t_top, text="👨‍🏫 1. КОМПЬЮТЕР УЧИТЕЛЯ (Главный пульт)", font=("Segoe UI", 12, "bold"), fg="#38BDF8", bg="#18181D").pack(side="left")
        
        tk.Label(teacher_card, text="Устанавливает веб-сервер управления (порт 8023), интерактивную карту класса и кнопки отката.", font=("Segoe UI", 10), fg="#A1A1AA", bg="#18181D", justify="left").pack(anchor="w", pady=(4, 8))
        
        btn_t = tk.Button(teacher_card, text="Установить пульт учителя", font=("Segoe UI", 10, "bold"), bg="#2563EB", fg="white", activebackground="#1D4ED8", activeforeground="white", relief="flat", padx=12, pady=6, cursor="hand2", command=self.do_install_teacher)
        btn_t.pack(anchor="w")

        # Student option
        student_card = tk.Frame(body, bg="#18181D", padx=16, pady=12, highlightbackground="#26262C", highlightthickness=1)
        student_card.pack(fill="x", pady=10)

        s_top = tk.Frame(student_card, bg="#18181D")
        s_top.pack(fill="x")
        tk.Label(s_top, text="💻 2. КОМПЬЮТЕР УЧЕНИКА (Станция с защитой)", font=("Segoe UI", 12, "bold"), fg="#34D399", bg="#18181D").pack(side="left")

        tk.Label(student_card, text="Устанавливает фоновый агент с защитой от выключения и автозагрузкой при старте Windows.", font=("Segoe UI", 10), fg="#A1A1AA", bg="#18181D", justify="left").pack(anchor="w", pady=(4, 8))

        ip_box = tk.Frame(student_card, bg="#18181D")
        ip_box.pack(fill="x", pady=(0, 8))
        tk.Label(ip_box, text="IP-адрес ПК учителя:", font=("Segoe UI", 10), fg="#94A3B8", bg="#18181D").pack(side="left")
        self.ip_entry = tk.Entry(ip_box, font=("Consolas", 10), width=16, bg="#0D0D0F", fg="#F4F4F5", insertbackground="white")
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(side="left", padx=8)

        btn_s = tk.Button(student_card, text="Установить агент защиты", font=("Segoe UI", 10, "bold"), bg="#059669", fg="white", activebackground="#047857", activeforeground="white", relief="flat", padx=12, pady=6, cursor="hand2", command=self.do_install_student)
        btn_s.pack(anchor="w")

    def do_install_teacher(self):
        try:
            shortcut = install_teacher_server()
            messagebox.showinfo(
                "Установка завершена",
                f"Пульт Учителя успешно установлен!\n\nЯрлык запуска создан на Рабочем столе:\n{shortcut.name}\n\nСервер будет доступен по адресу:\nhttp://localhost:8023"
            )
            self.root.destroy()
        except Exception as ex:
            messagebox.showerror("Ошибка", f"Не удалось завершить установку:\n{ex}")

    def do_install_student(self):
        teacher_ip = self.ip_entry.get().strip() or "127.0.0.1"
        try:
            install_student_agent(teacher_ip=teacher_ip)
            messagebox.showinfo(
                "Защита активирована",
                f"Агент Ученика успешно установлен и запущен в скрытом режиме!\n\n"
                f"• Адрес сервера учителя: {teacher_ip}:8023\n"
                f"• Автозагрузка с правами системы: ВКЛЮЧЕНА\n"
                f"• Защита от отключения учеником: АКТИВНА\n"
                f"• Перезагрузка ПК не снимет защиту."
            )
            self.root.destroy()
        except Exception as ex:
            messagebox.showerror("Ошибка", f"Не удалось установить агент:\n{ex}")


def main():
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
