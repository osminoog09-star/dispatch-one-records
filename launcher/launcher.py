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
VERSION = "1.1.0"
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

MANIFEST_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"


def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except Exception:
        return (0,)


def check_killswitch():
    """Стоп-кран: читает флаг enabled и минимальную версию из манифеста.
    Позволяет владельцу отключить копии/устаревшие сборки. (разрешено, причина)."""
    try:
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "lapd-launcher"})
        with urllib.request.urlopen(req, timeout=12) as r:
            m = json.load(r)
    except Exception:
        return True, ""   # нет связи — не блокируем (иначе оффлайн ломает всё)
    if m.get("enabled") is False:
        return False, "Доступ временно отключён руководством.\nОбратись к администратору."
    if _ver_tuple(VERSION) < _ver_tuple(m.get("min_launcher", "0")):
        return False, ("Эта версия лаунчера больше не поддерживается.\n"
                       "Скачай свежую с сайта департамента.")
    return True, ""


def check_update():
    """Читает version.json из репозитория. Возвращает dict:
       {launcher_new, agent_new, manifest} — что новее установленного."""
    try:
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "lapd-launcher"})
        with urllib.request.urlopen(req, timeout=15) as r:
            m = json.load(r)
    except Exception:
        log_exc("check_update")
        return {"launcher_new": False, "agent_new": False, "manifest": {}}

    cfg = read_config()
    agent_cur = cfg.get("AGENT_VERSION", "0")
    return {
        "launcher_new": _ver_tuple(m.get("launcher", "0")) > _ver_tuple(VERSION),
        "agent_new": _ver_tuple(m.get("agent", "0")) > _ver_tuple(agent_cur),
        "manifest": m,
    }


def _download(url, dst, on_progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "lapd-launcher"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dst, "wb") as f:
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


def update_agent(manifest, on_progress=None):
    """Скачивает новый агент, заменяет старый."""
    try:
        os.makedirs(INSTALL_DIR, exist_ok=True)
        tmp = os.path.join(INSTALL_DIR, AGENT_EXE + ".new")
        _download(manifest.get("agent_url"), tmp, on_progress)
        subprocess.run(["taskkill", "/F", "/IM", AGENT_EXE], capture_output=True,
                       creationflags=0x08000000)
        time.sleep(1)
        os.replace(tmp, os.path.join(INSTALL_DIR, AGENT_EXE))
        cfg = read_config()
        cfg["AGENT_VERSION"] = manifest.get("agent", "")
        write_config(cfg)
        log(f"агент обновлён до {manifest.get('agent')}")
        return True, f"Агент обновлён до {manifest.get('agent')}"
    except Exception as e:
        log_exc("update_agent")
        return False, f"Ошибка обновления агента: {e}"


def update_launcher(manifest, on_progress=None):
    """Самообновление: качает новый лаунчер и подменяет себя через bat."""
    try:
        cur = sys.executable  # путь к текущему .exe (в собранном виде)
        if not cur.lower().endswith(".exe"):
            return False, "самообновление только в собранной версии"
        new = cur + ".new"
        _download(manifest.get("launcher_url"), new, on_progress)
        # bat: ждёт закрытия, подменяет exe, запускает новый
        bat = os.path.join(INSTALL_DIR, "_update.bat")
        os.makedirs(INSTALL_DIR, exist_ok=True)
        with open(bat, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
            f.write("ping 127.0.0.1 -n 3 >nul\r\n")
            f.write(f'move /Y "{new}" "{cur}" >nul\r\n')
            f.write(f'start "" "{cur}"\r\n')
            f.write('del "%~f0"\r\n')
        log(f"самообновление до {manifest.get('launcher')}")
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
        return True, "restart"
    except Exception as e:
        log_exc("update_launcher")
        return False, f"Ошибка обновления лаунчера: {e}"


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


def _gh_api(path, payload, method="POST"):
    """Запрос к GitHub API вшитым ключом. (ok, ответ)."""
    token = get_embedded_token()
    if not token:
        return False, "нет ключа"
    import base64  # noqa
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/{path}",
                                 data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "lapd-launcher")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, json.load(r)
    except urllib.error.HTTPError as e:
        return False, f"{e.code}: {e.read().decode('utf-8','ignore')[:160]}"
    except Exception as e:
        return False, str(e)


def send_bug_report(description, screenshot_path=None):
    """Создаёт баг-репорт: скриншот и лог в репозиторий + Issue на GitHub. (ok, msg)."""
    import base64
    cfg = read_config()
    who = cfg.get("CALLSIGN", "?") + " / " + cfg.get("NICKNAME", "?")
    ts = time.strftime("%Y%m%d-%H%M%S")

    body = [f"**Офицер:** {who}",
            f"**Версия лаунчера:** {VERSION}",
            f"**Игра:** {find_game() or 'не найдена'}",
            "", "**Описание проблемы:**", description or "(без описания)", ""]

    # приложить скриншот в репозиторий (bug-reports/)
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            raw = open(screenshot_path, "rb").read()
            ext = os.path.splitext(screenshot_path)[1] or ".png"
            img_path = f"bug-reports/{ts}{ext}"
            ok, resp = _gh_api(f"contents/{img_path}", {
                "message": f"баг-репорт скриншот {ts}",
                "content": base64.b64encode(raw).decode("ascii")}, "PUT")
            if ok:
                url = f"https://github.com/{GITHUB_REPO}/blob/main/{img_path}?raw=true"
                body.append(f"**Скриншот:** {url}")
                body.append(f"![screenshot]({url})")
        except Exception as e:
            body.append(f"(скриншот не загрузился: {e})")

    # приложить хвост лога
    log_file = os.path.join(LOG_DIR, "launcher.log")
    if os.path.exists(log_file):
        tail = open(log_file, encoding="utf-8", errors="replace").read()[-1500:]
        body.append("\n**Лог (последнее):**\n```\n" + tail + "\n```")

    ok, resp = _gh_api("issues", {
        "title": f"[Баг] {who} — {ts}",
        "body": "\n".join(body),
        "labels": ["bug", "from-launcher"]})
    if ok:
        log(f"баг-репорт отправлен: {resp.get('html_url')}")
        return True, "Спасибо! Отчёт отправлен руководству."
    log(f"баг-репорт не отправлен: {resp}", "ERROR")
    return False, f"Не удалось отправить: {resp}"


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
            # вшитый агент = версия этого лаунчера
            cfg = read_config()
            cfg.setdefault("AGENT_VERSION", VERSION)
            write_config(cfg)
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

# ── палитра (тёмная тема в стиле GitHub) ──
BG      = "#0d1117"
CARD    = "#161b22"
CARD2   = "#1c232c"
BORDER  = "#30363d"
TEXT    = "#e6edf3"
MUTED   = "#8b949e"
ACCENT  = "#2f81f7"
ACCENT2 = "#4c8dff"
GREEN   = "#238636"
GREEN2  = "#2ea043"
OKGRN   = "#3fb950"
REDT    = "#f85149"


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("580x690")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.after(80, self._front)

        cfg = read_config()
        self.game = find_game()

        # ─── ШАПКА ───
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(26, 0))
        tk.Label(header, text="★", bg=ACCENT, fg="white",
                 font=("Segoe UI", 15, "bold"), width=2, height=1).pack()
        tk.Label(header, text="LAPD Records", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 24)).pack(pady=(10, 0))
        tk.Label(header, text=f"лаунчер · v{VERSION}", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack()

        # статус игры — плашка
        pill = tk.Label(self, bg=CARD, fg=OKGRN if self.game else REDT,
                        font=("Segoe UI", 9), padx=12, pady=5,
                        text="● игра найдена" if self.game else "● игра не найдена")
        pill.pack(pady=(12, 0))

        # ─── КАРТОЧКА: ПРОФИЛЬ ───
        card = self._card()
        card.pack(fill="x", padx=32, pady=(18, 0))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=18, pady=16)
        tk.Label(inner, text="ПРОФИЛЬ ОФИЦЕРА", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
        self.callsign = self._field(inner, "Позывной", cfg.get("CALLSIGN", ""))
        self.nickname = self._field(inner, "Имя офицера", cfg.get("NICKNAME", ""))
        self._button(inner, "Сохранить и прописать в игру",
                     self.save_identity, ACCENT, ACCENT2).pack(fill="x", pady=(12, 0))

        # ─── КАРТОЧКА: ОБНОВЛЕНИЯ ───
        upd = self._card()
        upd.pack(fill="x", padx=32, pady=(14, 0))
        ui = tk.Frame(upd, bg=CARD)
        ui.pack(fill="x", padx=18, pady=14)
        self.upd_label = tk.Label(ui, text="⟳  проверяю обновления…", bg=CARD, fg=MUTED,
                                  font=("Segoe UI", 9), anchor="w")
        self.upd_label.pack(fill="x")
        self.upd_notes = tk.Label(ui, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 8),
                                  anchor="w", justify="left", wraplength=480)
        self.upd_notes.pack(fill="x", pady=(2, 0))
        self.upd_btn = self._button(ui, "Проверить обновления", self.do_update,
                                    CARD2, BORDER, small=True)
        self.upd_btn.pack(anchor="w", pady=(10, 0))

        # ─── КНОПКА ИГРАТЬ ───
        self._button(self, "▶   ИГРАТЬ", self.play, GREEN, GREEN2,
                     big=True).pack(fill="x", padx=32, pady=(16, 4))
        tk.Label(self, text="запустит Vinewood и синхронизацию", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack()

        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.status.pack(pady=(8, 0))

        # ─── ФУТЕР ───
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(side="bottom", pady=14)
        for txt, cmd in (("🐞 Сообщить о проблеме", self.bug_report),
                         ("Открыть логи", self.open_logs), ("Открыть сайт", self.open_site)):
            b = tk.Label(bottom, text=txt, bg=BG, fg=MUTED, font=("Segoe UI", 8), cursor="hand2")
            b.pack(side="left", padx=10)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.config(fg=ACCENT))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=MUTED))

        ensure_agent_installed()
        log(f"лаунчер запущен v{VERSION}, игра={self.game}")
        threading.Thread(target=self._check_update_async, daemon=True).start()

    # ── строительные блоки UI ──
    def _card(self):
        return tk.Frame(self, bg=CARD, highlightbackground=BORDER, highlightthickness=1)

    def _front(self):
        try:
            self.attributes("-topmost", True); self.lift(); self.focus_force()
            self.after(500, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _field(self, parent, label, value):
        tk.Label(parent, text=label, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 3))
        wrap = tk.Frame(parent, bg=BORDER)
        wrap.pack(fill="x")
        e = tk.Entry(wrap, bg=CARD2, fg=TEXT, insertbackground=ACCENT,
                     relief="flat", font=("Segoe UI", 12))
        e.pack(fill="x", padx=1, pady=1, ipady=7)
        e.insert(0, value)
        e.bind("<FocusIn>", lambda ev: wrap.config(bg=ACCENT))
        e.bind("<FocusOut>", lambda ev: wrap.config(bg=BORDER))
        return e

    def _button(self, parent, text, cmd, color, hover, big=False, small=False):
        size = 14 if big else (9 if small else 11)
        pad = 14 if big else (7 if small else 10)
        b = tk.Button(parent, text=text, command=cmd, bg=color,
                      fg="white" if not small else TEXT,
                      activebackground=hover, activeforeground="white",
                      font=("Segoe UI Semibold", size), relief="flat",
                      padx=18, pady=pad, cursor="hand2", bd=0)
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=color))
        return b

    def _set_status(self, text, color="#98a1ac"):
        self.status.config(text=text, fg=color)

    def bug_report(self):
        """Окно баг-репорта: описание + скриншот → GitHub Issue."""
        from tkinter import filedialog
        dlg = tk.Toplevel(self)
        dlg.title("Сообщить о проблеме")
        dlg.geometry("460x440")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Сообщить о проблеме", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 15)).pack(pady=(18, 2))
        tk.Label(dlg, text="Опиши, что случилось. Можно приложить скриншот.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack()

        box = tk.Frame(dlg, bg=BORDER)
        box.pack(fill="both", expand=True, padx=24, pady=(14, 6))
        txt = tk.Text(box, bg=CARD2, fg=TEXT, insertbackground=ACCENT, relief="flat",
                      font=("Segoe UI", 10), height=7, wrap="word")
        txt.pack(fill="both", expand=True, padx=1, pady=1)

        shot = {"path": None}
        shot_lbl = tk.Label(dlg, text="скриншот не выбран", bg=BG, fg=MUTED,
                            font=("Segoe UI", 8))
        shot_lbl.pack()

        def pick():
            p = filedialog.askopenfilename(
                title="Выбери скриншот",
                filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp"), ("Все файлы", "*.*")])
            if p:
                shot["path"] = p
                shot_lbl.config(text="скриншот: " + os.path.basename(p), fg=OKGRN)

        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=24, pady=(4, 6))
        self._button(btns, "📎 Прикрепить скриншот", pick, CARD2, BORDER, small=True).pack(side="left")

        result = tk.Label(dlg, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=410)
        result.pack(pady=(2, 0))

        def send():
            desc = txt.get("1.0", "end").strip()
            if not desc:
                result.config(text="Опиши проблему — хотя бы пару слов.", fg=REDT)
                return
            result.config(text="Отправляю…", fg=MUTED)
            send_btn.config(state="disabled")
            def work():
                ok, msg = send_bug_report(desc, shot["path"])
                def done():
                    result.config(text=msg, fg=OKGRN if ok else REDT)
                    if ok:
                        dlg.after(1500, dlg.destroy)
                    else:
                        send_btn.config(state="normal")
                dlg.after(0, done)
            threading.Thread(target=work, daemon=True).start()

        send_btn = self._button(dlg, "Отправить отчёт", send, ACCENT, ACCENT2)
        send_btn.pack(fill="x", padx=24, pady=(4, 16))

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
        info = check_update()
        self._upd = info
        m = info.get("manifest") or {}
        def upd():
            notes = m.get("notes", "")
            if info.get("launcher_new"):
                self.upd_label.config(text=f"● Новая версия лаунчера: {m.get('launcher')}", fg="#e3b341")
                self.upd_btn.config(text=f"⬇ Обновить до {m.get('launcher')}")
                self.upd_notes.config(text=notes)
            elif info.get("agent_new"):
                self.upd_label.config(text=f"● Новая версия агента: {m.get('agent')}", fg="#e3b341")
                self.upd_btn.config(text=f"⬇ Обновить агент до {m.get('agent')}")
                self.upd_notes.config(text=notes)
            else:
                self.upd_label.config(text="✓ Установлена последняя версия.", fg=OKGRN)
                self.upd_notes.config(text=("Что нового: " + notes) if notes else "")
        self.after(0, upd)

    def do_update(self):
        info = getattr(self, "_upd", None)
        if not info or not (info.get("launcher_new") or info.get("agent_new")):
            self._set_status("Обновлений нет.", "#98a1ac")
            return
        m = info["manifest"]
        self.upd_btn.config(state="disabled", text="Скачиваю…")
        prog = lambda p: self.after(0, lambda: self.upd_label.config(text=f"Скачиваю… {int(p*100)}%"))

        def work():
            if info.get("launcher_new"):
                ok, msg = update_launcher(m, prog)
                if ok and msg == "restart":
                    self.after(0, lambda: (self._set_status("Лаунчер обновлён, перезапуск…", "#7fbf7f"),
                                           self.after(800, self.destroy)))
                    return
            else:
                ok, msg = update_agent(m, prog)
            def done():
                self._set_status(msg, "#7fbf7f" if ok else "#e0a0a0")
                self.upd_label.config(text="Готово." if ok else "Ошибка обновления.")
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
        allowed, reason = check_killswitch()
        if not allowed:
            import tkinter.messagebox as mb
            root = tk.Tk(); root.withdraw()
            mb.showerror(APP_NAME, reason)
            log(f"запуск заблокирован: {reason}", "WARN")
            sys.exit(0)
        Launcher().mainloop()
    except Exception:
        log_exc("main")
        raise
