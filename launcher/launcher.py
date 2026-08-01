"""
LAPD Records — лаунчер.
- Показывает и меняет позывной / имя (прописывает в игру).
- Проверяет и скачивает обновления агента с GitHub.
- Запускает агент синхронизации и лаунчер Vinewood.
- Ведёт лог всех действий и ошибок (для отслеживания багов).
"""
import os
import sys
import json
import time
import threading
import traceback
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import messagebox

APP_NAME = "LAPD Records"
VERSION = "1.0.0"
GITHUB_REPO = "osminoog09-star/dispatch-one-records"
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "DispatchOne")
CONFIG = os.path.join(INSTALL_DIR, "sync-config.ini")
LOG_DIR = os.path.join(INSTALL_DIR, "logs")
AGENT_EXE = "pdcomp_sync.exe"
VINEWOOD = r"C:\Program Files\Vinewood Launcher\Vinewood Launcher.exe"

GAME_CANDIDATES = [
    r"C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy",
    r"C:\Program Files\Rockstar Games\Grand Theft Auto V",
    r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V",
    r"D:\Games\Grand Theft Auto V",
]
CS_FILES = [
    ("plugins/LSPDFR/GrammarPolice/custom.ini", "Callsign", None),
    ("plugins/LSPDFR/CalloutInterface.ini", "MDTCallsign", None),
    ("plugins/LSPDFR/BlueLineScanner.ini", "VizLabel", None),
    ("plugins/LSPDFR/pdComp/config.ini", "Callsign", "Officer"),
]
NAME_FILE = ("plugins/LSPDFR/pdComp/config.ini", "Name", "Officer")


# ─────────────────────────── ЛОГ ───────────────────────────

def log(msg, level="INFO"):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}"
    try:
        with open(os.path.join(LOG_DIR, "launcher.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def log_exc(where):
    log(f"{where}: {traceback.format_exc()}", "ERROR")


# ─────────────────────── КОНФИГ ───────────────────────

def read_config():
    cfg = {}
    if os.path.exists(CONFIG):
        for ln in open(CONFIG, encoding="utf-8-sig"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def write_config(cfg):
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        f.write("# Настройки Dispatch One (лаунчер)\n")
        for k, v in cfg.items():
            f.write(f"{k}={v}\n")


def find_game():
    saved = read_config().get("GAME_DIR")
    if saved and os.path.isdir(os.path.join(saved, "plugins", "LSPDFR", "pdComp")):
        return saved
    for c in GAME_CANDIDATES:
        if os.path.isdir(os.path.join(c, "plugins", "LSPDFR", "pdComp")):
            return c
    return None


# ─────────────────── ПОЗЫВНОЙ / ИМЯ В ИГРЕ ───────────────────

def _set_ini(path, key, value, section=None):
    """Меняет значение ключа построчно (в нужной секции), добавляет если нет."""
    if not os.path.exists(path):
        return False
    import re
    lines = open(path, encoding="utf-8-sig").read().splitlines()
    out, cur, done = [], "", False
    skip_next = False
    for ln in lines:
        t = ln.strip()
        if skip_next:
            skip_next = False
            if t == value:
                continue
        if re.match(r"^\[(.+)\]$", t):
            cur = t[1:-1]
            out.append(ln)
            continue
        m = re.match(r"^([^\S\r\n]*)([A-Za-z0-9_]+)([^\S\r\n]*=[^\S\r\n]*)(.*)$", ln)
        if m and m.group(2).lower() == key.lower() and (not section or cur.lower() == section.lower()):
            sep = m.group(3) if "= " in m.group(3) else m.group(3).rstrip() + " "
            out.append(m.group(1) + m.group(2) + sep + value)
            done, skip_next = True, True
            continue
        out.append(ln)
    if not done:  # добавить ключ в секцию
        rebuilt, sec, ins = [], "", False
        for ln in out:
            rebuilt.append(ln)
            t = ln.strip()
            if re.match(r"^\[(.+)\]$", t):
                sec = t[1:-1]
                if not ins and (not section or sec.lower() == section.lower()):
                    rebuilt.append(f"{key} = {value}")
                    ins = True
        if ins:
            out = rebuilt
    with open(path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(out) + "\r\n")
    return True


def apply_identity(game, callsign, name):
    """Прописывает позывной и имя во все файлы игры. Возвращает список изменённых."""
    if not game:
        return []
    changed = []
    for rel, key, section in CS_FILES:
        p = os.path.join(game, rel.replace("/", os.sep))
        try:
            if _set_ini(p, key, callsign, section):
                changed.append(os.path.basename(rel))
        except PermissionError:
            log(f"нет прав на {rel} — нужен запуск от админа", "WARN")
        except Exception:
            log_exc(f"apply_identity {rel}")
    # имя офицера
    rel, key, section = NAME_FILE
    try:
        _set_ini(os.path.join(game, rel.replace("/", os.sep)), key, name, section)
    except Exception:
        log_exc("apply_identity name")
    return changed


# ─────────────────────── ОБНОВЛЕНИЯ ───────────────────────

def check_update():
    """Смотрит последний релиз на GitHub. Возвращает (есть_новее, тег, url_agent)."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lapd-launcher"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        tag = data.get("tag_name", "")
        agent_url = ""
        for a in data.get("assets", []):
            if a["name"] == AGENT_EXE:
                agent_url = a["browser_download_url"]
        cur = read_config().get("AGENT_VERSION", "")
        return (tag and tag != cur, tag, agent_url)
    except Exception:
        log_exc("check_update")
        return (False, "", "")


def download_update(agent_url, tag, on_progress=None):
    """Скачивает новый агент, заменяет старый."""
    try:
        os.makedirs(INSTALL_DIR, exist_ok=True)
        tmp = os.path.join(INSTALL_DIR, AGENT_EXE + ".new")
        req = urllib.request.Request(agent_url, headers={"User-Agent": "lapd-launcher"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            got = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if on_progress and total:
                    on_progress(got / total)
        dst = os.path.join(INSTALL_DIR, AGENT_EXE)
        # заменяем (если агент запущен — останавливаем)
        subprocess.run(["taskkill", "/F", "/IM", AGENT_EXE], capture_output=True,
                       creationflags=0x08000000)
        time.sleep(1)
        os.replace(tmp, dst)
        cfg = read_config()
        cfg["AGENT_VERSION"] = tag
        write_config(cfg)
        log(f"обновление установлено: {tag}")
        return True, f"Обновлено до {tag}"
    except Exception as e:
        log_exc("download_update")
        return False, f"Ошибка обновления: {e}"


# ─────────────────────── ЗАПУСК ───────────────────────

def _bundled(name):
    """Файл, вшитый в лаунчер (PyInstaller), или рядом со скриптом."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def get_embedded_token():
    """Ключ доступа, вшитый при сборке (в исходники не попадает)."""
    try:
        import embedded_token
        return embedded_token.get_token()
    except Exception:
        return ""


def ensure_agent_installed():
    """При первом запуске копирует вшитый агент в INSTALL_DIR."""
    exe = os.path.join(INSTALL_DIR, AGENT_EXE)
    if os.path.exists(exe):
        return
    src = _bundled(AGENT_EXE)
    if os.path.exists(src):
        try:
            os.makedirs(INSTALL_DIR, exist_ok=True)
            import shutil
            shutil.copy2(src, exe)
            log("агент установлен из комплекта")
        except Exception:
            log_exc("ensure_agent_installed")


def start_agent():
    exe = os.path.join(INSTALL_DIR, AGENT_EXE)
    if not os.path.exists(exe):
        ensure_agent_installed()
    if not os.path.exists(exe):
        return False, "агент не установлен"
    try:
        subprocess.Popen([exe], cwd=INSTALL_DIR,
                         creationflags=0x08000000)  # без окна
        log("агент запущен")
        return True, "агент запущен"
    except Exception as e:
        log_exc("start_agent")
        return False, str(e)


def start_vinewood():
    if os.path.exists(VINEWOOD):
        try:
            subprocess.Popen([VINEWOOD])
            log("Vinewood запущен")
            return True
        except Exception:
            log_exc("start_vinewood")
    return False


# ─────────────────────── ИНТЕРФЕЙС ───────────────────────

class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — лаунчер")
        self.geometry("560x620")
        self.resizable(False, False)
        self.configure(bg="#0f1216")
        self.after(80, self._front)

        cfg = read_config()
        self.game = find_game()

        tk.Label(self, text="LAPD Records", bg="#0f1216", fg="#e8ecf1",
                 font=("Segoe UI", 22, "bold")).pack(pady=(24, 2))
        tk.Label(self, text=f"лаунчер · v{VERSION}", bg="#0f1216", fg="#7f8994",
                 font=("Segoe UI", 9)).pack()

        game_txt = f"Игра: {self.game}" if self.game else "Игра не найдена!"
        tk.Label(self, text=game_txt, bg="#0f1216",
                 fg="#7fbf7f" if self.game else "#e0a0a0",
                 font=("Segoe UI", 8), wraplength=500).pack(pady=(8, 0))

        # поля позывного и имени
        frm = tk.Frame(self, bg="#0f1216")
        frm.pack(fill="x", padx=40, pady=16)
        self.callsign = self._field(frm, "Позывной", cfg.get("CALLSIGN", ""))
        self.nickname = self._field(frm, "Имя офицера", cfg.get("NICKNAME", ""))

        tk.Button(frm, text="💾 Сохранить и прописать в игру", command=self.save_identity,
                  bg="#3b82f6", fg="white", font=("Segoe UI", 11, "bold"),
                  relief="flat", padx=20, pady=9, cursor="hand2").pack(fill="x", pady=(6, 0))

        # обновления
        upd = tk.Frame(self, bg="#161b22", highlightbackground="#2a3038", highlightthickness=1)
        upd.pack(fill="x", padx=40, pady=6)
        self.upd_label = tk.Label(upd, text="Обновления: проверяю…", bg="#161b22", fg="#98a1ac",
                                  font=("Segoe UI", 9), anchor="w")
        self.upd_label.pack(fill="x", padx=12, pady=(10, 4))
        self.upd_btn = tk.Button(upd, text="Проверить обновления", command=self.do_update,
                                 bg="#232a33", fg="#e8ecf1", font=("Segoe UI", 9),
                                 relief="flat", padx=14, pady=6, cursor="hand2")
        self.upd_btn.pack(anchor="w", padx=12, pady=(0, 10))

        # играть
        tk.Button(self, text="▶  ИГРАТЬ  (Vinewood + синхронизация)", command=self.play,
                  bg="#1f9d55", fg="white", font=("Segoe UI", 13, "bold"),
                  relief="flat", padx=20, pady=13, cursor="hand2").pack(fill="x", padx=40, pady=(10, 6))

        self.status = tk.Label(self, text="", bg="#0f1216", fg="#98a1ac", font=("Segoe UI", 9))
        self.status.pack(pady=(4, 0))

        # ссылки
        bottom = tk.Frame(self, bg="#0f1216")
        bottom.pack(side="bottom", pady=12)
        tk.Button(bottom, text="Открыть логи", command=self.open_logs,
                  bg="#0f1216", fg="#6b7684", font=("Segoe UI", 8), relief="flat",
                  cursor="hand2", bd=0).pack(side="left", padx=8)
        tk.Button(bottom, text="Открыть сайт", command=self.open_site,
                  bg="#0f1216", fg="#6b7684", font=("Segoe UI", 8), relief="flat",
                  cursor="hand2", bd=0).pack(side="left", padx=8)

        ensure_agent_installed()
        log(f"лаунчер запущен v{VERSION}, игра={self.game}")
        threading.Thread(target=self._check_update_async, daemon=True).start()

    def _front(self):
        try:
            self.attributes("-topmost", True); self.lift(); self.focus_force()
            self.after(500, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _field(self, parent, label, value):
        tk.Label(parent, text=label, bg="#0f1216", fg="#98a1ac",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 2))
        e = tk.Entry(parent, bg="#1b2027", fg="#e8ecf1", insertbackground="#e8ecf1",
                     relief="flat", font=("Segoe UI", 11))
        e.pack(fill="x", ipady=6)
        e.insert(0, value)
        return e

    def _set_status(self, text, color="#98a1ac"):
        self.status.config(text=text, fg=color)

    def save_identity(self):
        cs = self.callsign.get().strip()
        nick = self.nickname.get().strip()
        if not cs or not nick:
            messagebox.showwarning(APP_NAME, "Заполни позывной и имя.")
            return
        cfg = read_config()
        cfg["CALLSIGN"], cfg["NICKNAME"] = cs, nick
        # первичная настройка отправки в GitHub (ключ вшит)
        cfg.setdefault("UPLOAD_MODE", "github")
        cfg.setdefault("GITHUB_REPO", GITHUB_REPO)
        cfg.setdefault("WATCH_GAME", "1")
        cfg.setdefault("AUTO_PUBLISH", "0")
        cfg.setdefault("POLL_SECONDS", "8")
        if "GITHUB_TOKEN" not in cfg:
            tok = get_embedded_token()
            if tok:
                cfg["GITHUB_TOKEN"] = tok
        if self.game:
            cfg["GAME_DIR"] = self.game
        write_config(cfg)
        changed = apply_identity(self.game, cs, nick)
        log(f"сохранён профиль: {cs} / {nick}, файлов изменено: {len(changed)}")
        if changed:
            self._set_status(f"Сохранено. Позывной прописан ({len(changed)} файлов).", "#7fbf7f")
        elif self.game:
            self._set_status("Сохранено, но файлы игры не изменены — запусти от админа.", "#e0a0a0")
        else:
            self._set_status("Сохранено. Игра не найдена — позывной не прописан.", "#e0a0a0")

    def _check_update_async(self):
        has, tag, url = check_update()
        self._pending_update = (tag, url) if has else None
        def upd():
            if has:
                self.upd_label.config(text=f"Доступно обновление: {tag}", fg="#e8d68a")
                self.upd_btn.config(text=f"⬇ Обновить до {tag}")
            else:
                self.upd_label.config(text="Установлена последняя версия.", fg="#7fbf7f")
        self.after(0, upd)

    def do_update(self):
        info = getattr(self, "_pending_update", None)
        if not info:
            self._set_status("Обновлений нет.", "#98a1ac")
            return
        tag, url = info
        self.upd_btn.config(state="disabled", text="Скачиваю…")
        def work():
            ok, msg = download_update(url, tag,
                                      on_progress=lambda p: self.after(0, lambda:
                                      self.upd_label.config(text=f"Скачиваю… {int(p*100)}%")))
            def done():
                self._set_status(msg, "#7fbf7f" if ok else "#e0a0a0")
                self.upd_label.config(text="Обновлено." if ok else "Ошибка обновления.")
                self.upd_btn.config(state="normal", text="Проверить обновления")
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def play(self):
        ok, msg = start_agent()
        self._set_status("Агент запущен. Открываю Vinewood…" if ok else f"Агент: {msg}",
                         "#7fbf7f" if ok else "#e0a0a0")
        start_vinewood()

    def open_logs(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        os.startfile(LOG_DIR)

    def open_site(self):
        os.startfile("https://osminoog09-star.github.io/dispatch-one-records/")


if __name__ == "__main__":
    try:
        Launcher().mainloop()
    except Exception:
        log_exc("main")
        raise
