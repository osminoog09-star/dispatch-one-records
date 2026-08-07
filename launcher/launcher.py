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
import shutil
import zipfile
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import messagebox

APP_NAME = "LAPD Records"
VERSION = "1.4.14"
GITHUB_REPO = "osminoog09-star/dispatch-one-records"
# Шлюз приёма данных (Cloudflare Worker) — вшивается при сборке, токена в клиенте нет.
try:
    import gateway_config
    GATEWAY_URL, GATEWAY_KEY = gateway_config.get()
except Exception:
    GATEWAY_URL = os.environ.get("DISPATCH_GATEWAY_URL", "")
    GATEWAY_KEY = os.environ.get("DISPATCH_GATEWAY_KEY", "")
# Supabase — чат-поддержка (publishable-ключ публичный, безопасен в клиенте)
SUPABASE_URL = "https://gwvqfiwdbviwoimvhdvg.supabase.co"
SUPABASE_KEY = "sb_publishable_gkXQmLngTvpGQfLFDk2YnA_nuv0krkk"
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


def _drives():
    import string
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.isdir(f"{d}:\\")]


def _reg_values(hive, key, names):
    out = []
    try:
        import winreg
        with winreg.OpenKey(hive, key) as k:
            for n in names:
                try:
                    v, _ = winreg.QueryValueEx(k, n)
                    if v:
                        out.append(v)
                except OSError:
                    pass
    except OSError:
        pass
    except Exception:
        pass
    return out


def _reg_gtav():
    """Путь установки GTA V из реестра Rockstar (Steam/Epic/Retail)."""
    try:
        import winreg
    except Exception:
        return []
    keys = [
        r"SOFTWARE\WOW6432Node\Rockstar Games\Grand Theft Auto V",
        r"SOFTWARE\Rockstar Games\Grand Theft Auto V",
        r"SOFTWARE\WOW6432Node\Rockstar Games\GTAV",
        r"SOFTWARE\Rockstar Games\GTAV",
    ]
    names = ["InstallFolder", "InstallFolderSteam", "InstallFolderEpic", "InstallFolderRetail"]
    out = []
    import winreg
    for key in keys:
        out += _reg_values(winreg.HKEY_LOCAL_MACHINE, key, names)
    return out


def _resolve_lnk(path):
    if not os.path.exists(path):
        return None
    try:
        ps = f'(New-Object -ComObject WScript.Shell).CreateShortcut("{path}").TargetPath'
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, creationflags=0x08000000, timeout=10)
        return (r.stdout or "").strip() or None
    except Exception:
        return None


# ─────────────────── Supabase: чат-поддержка ───────────────────

def _client_id():
    """Постоянный id этого установщика — по нему игрок видит свои тикеты."""
    cfg = read_config()
    cid = cfg.get("CLIENT_ID")
    if not cid:
        import uuid
        cid = str(uuid.uuid4())
        cfg["CLIENT_ID"] = cid
        write_config(cfg)
    return cid


def _sb(path, method="GET", body=None, prefer=None):
    """Запрос к Supabase REST с publishable-ключом и заголовкомx-client-id."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", "Bearer " + SUPABASE_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("x-client-id", _client_id())
    if prefer:
        req.add_header("Prefer", prefer)
    with urllib.request.urlopen(req, timeout=20) as r:
        t = r.read().decode("utf-8")
        return r.status, (json.loads(t) if t else None)


def sb_open_ticket_id():
    """id последнего открытого тикета этого игрока (или None)."""
    try:
        _, rows = _sb(f"tickets?client_id=eq.{_client_id()}&status=eq.open"
                      f"&select=id&order=created_at.desc&limit=1")
        return rows[0]["id"] if rows else None
    except Exception:
        log_exc("sb_open_ticket_id")
        return None


def sb_create_ticket(title):
    cfg = read_config()
    payload = {
        "title": title[:120] or "Обращение",
        "client_id": _client_id(),
        "callsign": cfg.get("CALLSIGN", ""),
        "created_by": cfg.get("NICKNAME") or cfg.get("CALLSIGN", "") or "Игрок",
        "category": "support",
        "source": "launcher",
    }
    try:
        _, rows = _sb("tickets", "POST", payload, prefer="return=representation")
    except urllib.error.HTTPError:
        # Старые базы без unified_tickets.sql не знают source/category.
        payload.pop("source", None)
        payload.pop("category", None)
        _, rows = _sb("tickets", "POST", payload, prefer="return=representation")
    return rows[0]["id"] if rows else None


def sb_add_comment(ticket_id, body, attachment_url=None):
    cfg = read_config()
    payload = {
        "ticket_id": ticket_id,
        "client_id": _client_id(),
        "body": body,
        "author": cfg.get("NICKNAME") or cfg.get("CALLSIGN", "") or "Игрок",
        "attachment_url": attachment_url,
        "source": "launcher",
    }
    try:
        _sb("ticket_comments", "POST", payload)
    except urllib.error.HTTPError:
        payload.pop("source", None)
        _sb("ticket_comments", "POST", payload)


def sb_list_comments(ticket_id):
    try:
        _, rows = _sb(f"ticket_comments?ticket_id=eq.{ticket_id}"
                      f"&select=body,from_admin,author,created_at,attachment_url&order=created_at")
        return rows or []
    except Exception:
        return []


def sb_close_ticket(ticket_id):
    try:
        _sb(f"tickets?id=eq.{ticket_id}", "PATCH", {"status": "closed"})
        return True
    except Exception:
        return False


def sb_upload(name, data_bytes, content_type):
    """Загружает вложение в bucket support, возвращает публичный URL."""
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/support/{name}"
        req = urllib.request.Request(url, data=data_bytes, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", "Bearer " + SUPABASE_KEY)
        req.add_header("Content-Type", content_type)
        req.add_header("x-upsert", "true")
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status in (200, 201):
                return f"{SUPABASE_URL}/storage/v1/object/public/support/{name}"
    except Exception:
        log_exc("sb_upload")
    return None


def find_game():
    """Авто-поиск папки игры: сохранённый путь → реестр → кандидаты → скан дисков.
    Годится папка с plugins\\LSPDFR\\pdComp ИЛИ с RAGEPluginHook.exe."""
    def ok(p):
        return bool(p) and (os.path.isdir(os.path.join(p, "plugins", "LSPDFR", "pdComp"))
                            or os.path.exists(os.path.join(p, "RAGEPluginHook.exe")))
    saved = read_config().get("GAME_DIR")
    if ok(saved):
        return saved
    for p in _reg_gtav():
        if ok(p):
            return p
    for c in GAME_CANDIDATES:
        if ok(c):
            return c
    subs = [
        r"Program Files\Rockstar Games\Grand Theft Auto V Legacy",
        r"Program Files\Rockstar Games\Grand Theft Auto V",
        r"Rockstar Games\Grand Theft Auto V Legacy",
        r"Rockstar Games\Grand Theft Auto V",
        r"Steam\steamapps\common\Grand Theft Auto V",
        r"SteamLibrary\steamapps\common\Grand Theft Auto V",
        r"Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V",
        r"Epic Games\GTAV", r"Games\Grand Theft Auto V", r"Grand Theft Auto V",
    ]
    for drive in _drives():
        for s in subs:
            p = os.path.join(drive, s)
            if ok(p):
                return p
    return None


def find_vinewood():
    """Авто-поиск Vinewood Launcher.exe: сохранённый → типовые пути → ярлык → скан дисков."""
    saved = read_config().get("VINEWOOD_EXE")
    if saved and os.path.exists(saved):
        return saved
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [
        r"C:\Program Files\Vinewood Launcher\Vinewood Launcher.exe",
        r"C:\Program Files (x86)\Vinewood Launcher\Vinewood Launcher.exe",
        os.path.join(la, "Programs", "Vinewood Launcher", "Vinewood Launcher.exe"),
        os.path.join(la, "Vinewood Launcher", "Vinewood Launcher.exe"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    tgt = _resolve_lnk(os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                    "Start Menu", "Programs", "Vinewood Launcher.lnk"))
    if tgt and os.path.exists(tgt):
        return tgt
    for drive in _drives():
        for base in ("Program Files", "Program Files (x86)"):
            p = os.path.join(drive, base, "Vinewood Launcher", "Vinewood Launcher.exe")
            if os.path.exists(p):
                return p
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
    """Самообновление: поддерживает старый exe и новый onedir zip-релиз."""
    try:
        cur = sys.executable  # путь к текущему .exe (в собранном виде)
        if not cur.lower().endswith(".exe"):
            return False, "самообновление только в собранной версии"

        url = manifest.get("launcher_url") or ""
        bat = os.path.join(INSTALL_DIR, "_update.bat")
        os.makedirs(INSTALL_DIR, exist_ok=True)

        if url.lower().endswith(".zip"):
            zip_path = os.path.join(INSTALL_DIR, "LAPD-Records-Launcher.zip")
            stage = os.path.join(INSTALL_DIR, "launcher_update")
            _download(url, zip_path, on_progress)
            if os.path.isdir(stage):
                shutil.rmtree(stage, ignore_errors=True)
            os.makedirs(stage, exist_ok=True)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(stage)

            cur_dir = os.path.dirname(cur)
            if os.path.exists(os.path.join(cur_dir, "_internal")):
                target_dir = cur_dir
            else:
                target_dir = os.path.join(INSTALL_DIR, "Launcher")
            new_exe = os.path.join(target_dir, "LAPD-Records-Launcher.exe")
            os.makedirs(target_dir, exist_ok=True)

            with open(bat, "w", encoding="utf-8") as f:
                f.write("@echo off\r\n")
                f.write("ping 127.0.0.1 -n 3 >nul\r\n")
                f.write(f'xcopy /E /I /Y "{stage}\\*" "{target_dir}\\" >nul\r\n')
                f.write(f'start "" "{new_exe}"\r\n')
                f.write('del "%~f0"\r\n')
            log(f"самообновление onedir до {manifest.get('launcher')}")
            subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
            return True, "restart"

        new = cur + ".new"
        _download(url, new, on_progress)
        # bat: ждёт закрытия, подменяет exe, запускает новый
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
    """Файл, вшитый в PyInstaller, лежащий рядом с .exe или рядом со скриптом."""
    roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(meipass)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        roots.append(exe_dir)
        roots.append(os.path.join(exe_dir, "_internal"))
    roots.append(os.path.dirname(os.path.abspath(__file__)))
    for base in roots:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return os.path.join(roots[0], name)


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
    if is_agent_running():
        return True, "агент уже запущен"
    try:
        subprocess.Popen([exe], cwd=INSTALL_DIR,
                         creationflags=0x08000000)  # без окна
        log("агент запущен")
        return True, "агент запущен"
    except Exception as e:
        log_exc("start_agent")
        return False, str(e)


def is_agent_running():
    """True, если процесс агента уже висит в системе."""
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {AGENT_EXE}"],
                           capture_output=True, text=True, creationflags=0x08000000)
        return AGENT_EXE.lower() in (r.stdout or "").lower()
    except Exception:
        log_exc("is_agent_running")
        return False


def stop_agent():
    """Останавливает агент синхронизации вручную из лаунчера."""
    if not is_agent_running():
        return True, "агент уже выключен"
    try:
        r = subprocess.run(["taskkill", "/F", "/IM", AGENT_EXE],
                           capture_output=True, text=True, creationflags=0x08000000)
        if r.returncode == 0:
            log("агент остановлен")
            return True, "агент выключен"
        msg = (r.stderr or r.stdout or "").strip() or f"код {r.returncode}"
        log(f"агент не остановлен: {msg}", "WARN")
        return False, msg
    except Exception as e:
        log_exc("stop_agent")
        return False, str(e)


def start_vinewood():
    exe = find_vinewood()
    if exe:
        try:
            subprocess.Popen([exe])
            log(f"Vinewood запущен: {exe}")
            return True
        except Exception:
            log_exc("start_vinewood")
    return False


PLUGIN_DLL = "DispatchOne.MDT.dll"


def _plugin_source():
    """Ищет собранный плагин: вшитый в лаунчер, рядом, или в репозитории."""
    for p in (_bundled(PLUGIN_DLL),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), PLUGIN_DLL),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "dispatch-plugin", "out", PLUGIN_DLL)):
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


def install_plugin(game):
    """Копирует плагин в plugins\\LSPDFR игры (лаунчер идёт от админа). (ok, msg)."""
    if not game:
        return False, "игра не найдена"
    src = _plugin_source()
    if not src:
        return False, "файл плагина не найден в комплекте"
    dst_dir = os.path.join(game, "plugins", "LSPDFR")
    if not os.path.isdir(dst_dir):
        return False, "нет папки plugins\\LSPDFR (установлен ли LSPDFR?)"
    dst = os.path.join(dst_dir, PLUGIN_DLL)
    try:
        # не перезаписываем, если тот же по размеру и не старее
        if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src) \
                and os.path.getmtime(dst) >= os.path.getmtime(src):
            return True, "плагин уже установлен"
        import shutil
        shutil.copy2(src, dst)
        log(f"плагин установлен: {dst}")
        return True, "плагин установлен"
    except PermissionError:
        log("нет прав на установку плагина — нужен запуск от админа", "WARN")
        return False, "нет прав — запусти лаунчер от администратора"
    except Exception as e:
        log_exc("install_plugin")
        return False, str(e)


def launch_game(game):
    """Запускает модовую игру через RagePluginHook (грузит LSPDFR + плагин). (ok, msg)."""
    if not game:
        return False, "игра не найдена"
    for exe in ("RAGEPluginHook.exe", "RAGEPluginHook64.exe"):
        p = os.path.join(game, exe)
        if os.path.exists(p):
            try:
                subprocess.Popen([p], cwd=game)
                log(f"игра запущена через {exe}")
                return True, "игра запускается через RagePluginHook"
            except Exception as e:
                log_exc("launch_game")
                return False, str(e)
    return False, "RagePluginHook.exe не найден в папке игры"


# ─────────────── автозапуск агента с Windows ───────────────

def _startup_lnk():
    startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup")
    return os.path.join(startup, "LAPD Records Agent.lnk")


def autostart_enabled():
    return os.path.exists(_startup_lnk())


def set_autostart(enable):
    """Вкл/выкл автозапуск АГЕНТА с Windows (ярлык в Автозагрузке).
    Тогда агент сам ловит запуск игры — через Vinewood, Steam, как угодно."""
    lnk = _startup_lnk()
    try:
        if enable:
            ensure_agent_installed()
            exe = os.path.join(INSTALL_DIR, AGENT_EXE)
            ps = (f'$w=New-Object -ComObject WScript.Shell;'
                  f'$s=$w.CreateShortcut("{lnk}");$s.TargetPath="{exe}";'
                  f'$s.WorkingDirectory="{INSTALL_DIR}";$s.Save()')
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, creationflags=0x08000000)
            # запустить сразу, если не запущен
            start_agent()
            log("автозапуск агента включён")
        else:
            if os.path.exists(lnk):
                os.remove(lnk)
            log("автозапуск агента выключен")
        return True
    except Exception:
        log_exc("set_autostart")
        return False


# ─────────────── полное удаление с компьютера ───────────────

def _safe_in_install_dir(path):
    try:
        base = os.path.abspath(INSTALL_DIR)
        target = os.path.abspath(path)
        return target == base or target.startswith(base + os.sep)
    except Exception:
        return False


def _known_shortcuts():
    names = [
        "LAPD-Records-Launcher.lnk",
        "LAPD Records.lnk",
        "Dispatch One.lnk",
        "LAPD Records Agent.lnk",
    ]
    roots = [
        os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop"),
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup"),
    ]
    result = []
    for root in roots:
        for name in names:
            result.append(os.path.join(root, name))
    result.append(_startup_lnk())
    return result


def remove_game_plugin(game):
    if not game:
        return
    dll = os.path.join(game, "plugins", "LSPDFR", PLUGIN_DLL)
    try:
        if os.path.exists(dll):
            os.remove(dll)
            log(f"плагин удалён из игры: {dll}")
    except Exception:
        log_exc("remove_game_plugin")


def uninstall_local_files(game=None):
    """Removes shortcuts/plugin now and schedules INSTALL_DIR removal after exit."""
    try:
        stop_agent()
        set_autostart(False)
        remove_game_plugin(game)
        for lnk in set(_known_shortcuts()):
            try:
                if os.path.exists(lnk):
                    os.remove(lnk)
                    log(f"ярлык удалён: {lnk}")
            except Exception:
                log_exc("remove shortcut")

        if not _safe_in_install_dir(INSTALL_DIR):
            return False, "путь установки выглядит небезопасно, удаление остановлено"

        bat = os.path.join(os.environ.get("TEMP", INSTALL_DIR), f"lapd_records_uninstall_{os.getpid()}.bat")
        script = (
            "@echo off\r\n"
            "chcp 65001 >nul\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'taskkill /F /IM "{AGENT_EXE}" >nul 2>nul\r\n'
            ":again\r\n"
            f'rmdir /s /q "{INSTALL_DIR}" >nul 2>nul\r\n'
            f'if exist "{INSTALL_DIR}" (\r\n'
            "  timeout /t 1 /nobreak >nul\r\n"
            "  goto again\r\n"
            ")\r\n"
            'del "%~f0" >nul 2>nul\r\n'
        )
        with open(bat, "w", encoding="utf-8") as f:
            f.write(script)
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
        log("полное удаление запланировано после закрытия лаунчера")
        return True, "Лаунчер удалится после закрытия окна"
    except Exception:
        log_exc("uninstall_local_files")
        return False, "не удалось запустить удаление, открой логи"


# ─────────────────────── ИНТЕРФЕЙС ───────────────────────

# ── палитра: премиальная тёмная MDT-тема с холодным LAPD-свечением ──
BG      = "#070b12"
CARD    = "#111923"
CARD2   = "#172231"
BORDER  = "#26364a"
TEXT    = "#edf5ff"
MUTED   = "#96a4b8"
ACCENT  = "#2f81f7"
ACCENT2 = "#62a7ff"
GREEN   = "#1f8f3a"
GREEN2  = "#31b45a"
OKGRN   = "#4dd176"
REDT    = "#ff5d66"
WINDOW_W = 860
WINDOW_MIN_H = 700
CONTENT_WRAP = 620


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry(f"{WINDOW_W}x760")
        self.minsize(WINDOW_W, WINDOW_MIN_H)
        self.resizable(True, True)
        self.configure(bg=BG)
        self._closing = False
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(80, self._front)

        cfg = read_config()
        self.game = find_game()
        self._nav_buttons = {}

        # ─── баннер: полицейский крузер с мигалкой (анимированная картинка) ───
        self._frames = []
        for nm in ("banner_red.png", "banner_blue.png"):
            p = _bundled(nm)
            try:
                if os.path.exists(p):
                    self._frames.append(tk.PhotoImage(file=p))
            except Exception:
                log_exc("load banner")
        if self._frames:
            self.hero = tk.Label(self, image=self._frames[0], bg=BG, bd=0)
            self.hero.pack(fill="x")
            self._frame_i = 0
            self.after(200, self._animate_hero)

        # ─── ШАПКА ───
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=24, pady=(10 if self._frames else 22, 0))
        if self._frames:
            tk.Label(header, text=f"LAPD Records · лаунчер v{VERSION}", bg=BG, fg=TEXT,
                     font=("Segoe UI Semibold", 13)).pack(anchor="w")
            tk.Label(header, text="разделы: запуск, профиль, агент, поддержка, настройки и инструкция",
                     bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
        else:
            tk.Label(header, text="★", bg=ACCENT, fg="white",
                     font=("Segoe UI", 15, "bold"), width=2, height=1).pack()
            tk.Label(header, text="LAPD Records", bg=BG, fg=TEXT,
                     font=("Segoe UI Semibold", 24)).pack(pady=(10, 0))
            tk.Label(header, text=f"лаунчер · v{VERSION}", bg=BG, fg=MUTED,
                     font=("Segoe UI", 9)).pack()

        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        self.close_agent_var = tk.BooleanVar(
            value=cfg.get("CLOSE_AGENT_WITH_LAUNCHER", "1").lower() not in ("0", "false", "no")
        )

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=24, pady=(14, 8))
        nav = tk.Frame(shell, bg=BG, width=185)
        nav.pack(side="left", fill="y", padx=(0, 14))
        nav.pack_propagate(False)
        self.body = tk.Frame(shell, bg=BG)
        self.body.pack(side="left", fill="both", expand=True)

        for key, label in (
            ("home", "Главная"),
            ("profile", "Профиль"),
            ("agent", "Агент"),
            ("support", "Поддержка"),
            ("settings", "Настройки"),
            ("help", "Инструкция"),
        ):
            b = tk.Button(nav, text=label, command=lambda k=key: self.show_section(k),
                          bg=CARD2, fg=TEXT, activebackground=ACCENT,
                          activeforeground="white", relief="flat", bd=0,
                          font=("Segoe UI Semibold", 10), anchor="w",
                          padx=14, pady=10, cursor="hand2")
            b.pack(fill="x", pady=(0, 7))
            self._nav_buttons[key] = b

        nav_status = tk.Frame(nav, bg=BG)
        nav_status.pack(side="bottom", fill="x", pady=(10, 0))
        tk.Frame(nav_status, bg=BORDER, height=1).pack(fill="x", pady=(0, 10))
        self.game_state = tk.Label(nav_status, bg=BG, fg=OKGRN if self.game else REDT,
                                   text="● игра найдена" if self.game else "● игра не найдена",
                                   font=("Segoe UI", 8, "bold"), anchor="w")
        self.game_state.pack(fill="x", pady=(0, 6))
        self.nav_agent_state = tk.Label(nav_status, bg=BG, fg=MUTED, text="● агент: проверяю",
                                        font=("Segoe UI", 8, "bold"), anchor="w")
        self.nav_agent_state.pack(fill="x")

        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=24, pady=(0, 8))
        self._upd_text = "⟳  проверяю обновления…"
        self._upd_fg = MUTED
        self._upd_notes_text = ""

        self.show_section("home")
        self._refresh_agent_status()

        # ─── ФУТЕР ───
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(side="bottom", pady=(0, 12))
        for txt, cmd in (("Поддержка", self.support_chat),
                         ("Открыть логи", self.open_logs), ("Открыть сайт", self.open_site)):
            b = tk.Label(bottom, text=txt, bg=BG, fg=MUTED, font=("Segoe UI", 8), cursor="hand2")
            b.pack(side="left", padx=10)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.config(fg=ACCENT))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=MUTED))

        ensure_agent_installed()
        # ставим плагин сразу — тогда он грузится при ЛЮБОМ запуске игры
        # (наш лаунчер, Vinewood, Steam) как обычный плагин LSPDFR
        # установку плагина делаем В ФОНЕ — копирование в Program Files + скан антивируса
        # не должны подвешивать окно («Не отвечает»)
        if self.game:
            threading.Thread(target=self._startup_install_plugin, daemon=True).start()
        log(f"лаунчер запущен v{VERSION}, игра={self.game}")
        threading.Thread(target=self._check_update_async, daemon=True).start()
        if cfg.get("ONBOARDING_DONE", "0").lower() not in ("1", "true", "yes"):
            self.after(350, self.show_onboarding)
        self.after(60, self._fit_height)

    def _fit_height(self):
        """Подгоняет высоту окна под реальную высоту контента (не больше экрана)."""
        try:
            self.update_idletasks()
            need = self.winfo_reqheight()
            maxh = self.winfo_screenheight() - 90
            self.geometry("%dx%d" % (max(self.winfo_width(), WINDOW_W), min(max(need, WINDOW_MIN_H), maxh)))
        except Exception:
            log_exc("_fit_height")

    def show_section(self, key):
        for child in self.body.winfo_children():
            child.destroy()
        for name, btn in self._nav_buttons.items():
            btn.config(bg=ACCENT if name == key else CARD2,
                       fg="white" if name == key else TEXT)

        builders = {
            "home": self.build_home,
            "profile": self.build_profile,
            "agent": self.build_agent,
            "support": self.build_support,
            "settings": self.build_settings,
            "help": self.build_help,
        }
        builders.get(key, self.build_home)()
        self.after(40, self._fit_height)

    def _section_title(self, parent, title, subtitle):
        tk.Label(parent, text=title, bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        if subtitle:
            tk.Label(parent, text=subtitle, bg=BG, fg=MUTED,
                     font=("Segoe UI", 9), wraplength=CONTENT_WRAP, justify="left").pack(anchor="w", pady=(3, 14))

    def _card(self, parent=None):
        return tk.Frame(parent or self, bg=CARD, highlightbackground=BORDER, highlightthickness=1)

    def build_home(self):
        self._section_title(self.body, "Главная / Играть",
                            "Быстрый запуск GTA V через Vinewood, установка плагина и синхронизация патруля.")
        card = self._card(self.body)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=18, pady=18)
        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="Статус", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.home_game_state = tk.Label(row, text="● игра найдена" if self.game else "● игра не найдена",
                                        bg=CARD, fg=OKGRN if self.game else REDT,
                                        font=("Segoe UI Semibold", 12), anchor="w")
        self.home_game_state.pack(fill="x", pady=(4, 0))
        self.home_agent_state = tk.Label(row, text="● агент: проверяю",
                                         bg=CARD, fg=MUTED,
                                         font=("Segoe UI", 9, "bold"), anchor="w")
        self.home_agent_state.pack(fill="x", pady=(3, 12))

        self._button(inner, "▶   ИГРАТЬ", self.play, GREEN, GREEN2, big=True).pack(fill="x")
        tk.Label(inner, text="Лаунчер поставит плагин, запустит агент и откроет игру через Vinewood. "
                             "Если Vinewood не найден, попробует RagePluginHook.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=CONTENT_WRAP,
                 justify="left").pack(anchor="w", pady=(10, 0))

    def build_profile(self):
        cfg = read_config()
        self._section_title(self.body, "Профиль офицера",
                            "Позывной и имя должны совпадать с ростером сервера, иначе записи могут уйти на модерацию.")
        card = self._card(self.body)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=18, pady=16)
        self.callsign = self._field(inner, "Позывной", cfg.get("CALLSIGN", ""))
        self.nickname = self._field(inner, "Имя офицера", cfg.get("NICKNAME", ""))
        tk.Label(inner, text="Пример правильно: 7-WILLIAM-1. Неправильно: 7 - WILIAM - 1.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=CONTENT_WRAP,
                 justify="left").pack(anchor="w", pady=(8, 0))
        self._button(inner, "Сохранить и прописать в игру",
                     self.save_identity, ACCENT, ACCENT2).pack(fill="x", pady=(12, 0))

    def build_agent(self):
        self._section_title(self.body, "Агент синхронизации",
                            "Фоновый процесс читает pdComp, ловит запуск игры и отправляет данные на сайт.")
        card = self._card(self.body)
        card.pack(fill="x")
        ag = tk.Frame(card, bg=CARD)
        ag.pack(fill="x", padx=18, pady=16)
        top = tk.Frame(ag, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text="Процесс", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.agent_state = tk.Label(top, text="● проверяю", bg=CARD, fg=MUTED,
                                    font=("Segoe UI", 9, "bold"))
        self.agent_state.pack(side="right")
        tk.Label(ag, text="Можно запускать игру как угодно: через кнопку ИГРАТЬ, Vinewood или Steam. "
                          "Агент сам найдёт сессию, если включён.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=CONTENT_WRAP,
                 justify="left").pack(anchor="w", pady=(6, 10))
        tk.Checkbutton(ag, text="  Автозапуск с Windows",
                       variable=self.autostart_var, command=self.toggle_autostart,
                       bg=CARD, fg=TEXT, selectcolor=CARD2, activebackground=CARD,
                       activeforeground=TEXT, font=("Segoe UI", 9), anchor="w").pack(fill="x")
        tk.Checkbutton(ag, text="  Закрывать агент вместе с лаунчером",
                       variable=self.close_agent_var, command=self.save_agent_close_pref,
                       bg=CARD, fg=TEXT, selectcolor=CARD2, activebackground=CARD,
                       activeforeground=TEXT, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(2, 12))
        row = tk.Frame(ag, bg=CARD)
        row.pack(fill="x")
        self.agent_btn = self._button(row, "Включить агент", self.toggle_agent, ACCENT, ACCENT2, small=True)
        self.agent_btn.pack(side="left", fill="x", expand=True)
        self._button(row, "Открыть логи", self.open_logs, CARD2, BORDER, small=True).pack(
            side="left", fill="x", expand=True, padx=(8, 0))

    def build_support(self):
        self._section_title(self.body, "Поддержка",
                            "Если записи не появились, агент ругается или игра не запускается — напиши сюда.")
        card = self._card(self.body)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=18, pady=16)
        self._button(inner, "Открыть чат поддержки", self.support_chat, ACCENT, ACCENT2).pack(fill="x")
        tk.Label(inner, text="Чат приложит RagePluginHook.log, если он найден. "
                             "Оператор увидит описание, лог и сможет ответить прямо в тикете.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=CONTENT_WRAP,
                 justify="left").pack(anchor="w", pady=(10, 0))
        self._button(inner, "Открыть папку логов", self.open_logs, CARD2, BORDER, small=True).pack(fill="x", pady=(12, 0))

    def build_settings(self):
        self._section_title(self.body, "Настройки",
                            "Пути, обновления и служебные действия. Обычно менять ничего не нужно.")
        card = self._card(self.body)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=18, pady=16)
        tk.Label(inner, text="Игра", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(inner, text=self.game or "GTA V не найдена автоматически",
                 bg=CARD, fg=TEXT if self.game else REDT, font=("Segoe UI", 9),
                 wraplength=CONTENT_WRAP, justify="left").pack(anchor="w", pady=(3, 12))
        tk.Label(inner, text="Обновления", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.upd_label = tk.Label(inner, text=self._upd_text, bg=CARD, fg=self._upd_fg,
                                  font=("Segoe UI", 9), anchor="w")
        self.upd_label.pack(fill="x", pady=(3, 0))
        self.upd_notes = tk.Label(inner, text=self._upd_notes_text, bg=CARD, fg=MUTED, font=("Segoe UI", 8),
                                  anchor="w", justify="left", wraplength=CONTENT_WRAP)
        self.upd_notes.pack(fill="x", pady=(2, 10))
        self.upd_btn = self._button(inner, "Проверить обновления", self.do_update, CARD2, BORDER, small=True)
        self.upd_btn.pack(fill="x")
        self._button(inner, "Открыть сайт", self.open_site, CARD2, BORDER, small=True).pack(fill="x", pady=(8, 0))

        danger = self._card(self.body)
        danger.pack(fill="x", pady=(12, 0))
        din = tk.Frame(danger, bg=CARD)
        din.pack(fill="x", padx=18, pady=16)
        tk.Label(din, text="Полное удаление", bg=CARD, fg=REDT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(din, text=("Удалит локальный лаунчер, агент синхронизации, автозапуск, ярлыки, "
                            "логи и настройки с этого компьютера. Записи на сайте не удаляются."),
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=CONTENT_WRAP,
                 justify="left").pack(anchor="w", pady=(3, 10))
        self._button(din, "Удалить LAPD-Records-Launcher с ПК",
                     self.full_uninstall, "#5f1f29", "#8b2a36", small=True).pack(fill="x")

    def build_help(self):
        self._section_title(self.body, "Инструкция / Как это работает", "")
        card = self._card(self.body)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        text_wrap = tk.Frame(inner, bg=BORDER)
        text_wrap.pack(fill="both", expand=True)
        txt = tk.Text(text_wrap, bg=CARD, fg=TEXT, relief="flat", bd=0,
                      highlightthickness=0, insertbackground=ACCENT,
                      font=("Segoe UI", 9), wrap="word", padx=14, pady=12,
                      height=20, spacing1=2, spacing3=8)
        sb = tk.Scrollbar(text_wrap, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.insert("1.0", self.instruction_text())
        txt.configure(state="disabled", cursor="arrow")
        txt.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        sb.pack(side="right", fill="y", padx=(0, 1), pady=1)

    def instruction_text(self):
        return (
            "Что это.\n"
            "LAPD Records — лаунчер для GTA V LSPDFR. Он ставит плагин учёта, запускает игру "
            "через Vinewood и синхронизирует полицейскую активность на сайт.\n\n"
            "Профиль.\n"
            "Впиши позывной и имя офицера. Позывной должен точно совпадать с ростером сервера: "
            "например 7-WILLIAM-1, без лишних пробелов и ошибок.\n\n"
            "Агент.\n"
            "pdcomp_sync.exe — фоновая программа. Она ловит игру, читает pdComp и отправляет данные "
            "на сайт. Агент можно запускать с Windows и закрывать вместе с лаунчером.\n\n"
            "Как играть.\n"
            "Нажми ИГРАТЬ. Лаунчер поставит плагин, включит агент и откроет игру через Vinewood. "
            "Играй как обычно; после выхода из игры записи появятся на сайте.\n\n"
            "Где мои записи.\n"
            "На сайте открой профиль по своему позывному: там будут аресты, штрафы, вызовы, суды и смены.\n\n"
            "Логи и поддержка.\n"
            "Если что-то не работает, открой раздел Поддержка. Лог RagePluginHook.log приложится к обращению, "
            "а ответ оператора появится в этом же чате.\n\n"
            "Если ничего не появилось.\n"
            "Проверь позывной, статус агента и то, что игра была закрыта после смены. Если не помогло — отправь лог."
        )

    def show_onboarding(self):
        dlg = tk.Toplevel(self)
        dlg.title("Добро пожаловать")
        dlg.geometry("520x560")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        tk.Label(dlg, text="Добро пожаловать в LAPD Records", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 17)).pack(anchor="w", padx=22, pady=(20, 6))
        box = tk.Frame(dlg, bg=BORDER)
        box.pack(fill="both", expand=True, padx=22, pady=(0, 8))
        txt = tk.Text(box, bg=CARD, fg=TEXT, relief="flat", bd=0,
                      highlightthickness=0, font=("Segoe UI", 9),
                      wrap="word", padx=14, pady=12, height=18,
                      spacing1=2, spacing3=8)
        txt.insert("1.0", self.instruction_text())
        txt.configure(state="disabled", cursor="arrow")
        txt.pack(fill="both", expand=True, padx=1, pady=1)

        def done():
            cfg = read_config()
            cfg["ONBOARDING_DONE"] = "1"
            write_config(cfg)
            dlg.destroy()

        self._button(dlg, "Понятно, начать", done, ACCENT, ACCENT2).pack(fill="x", padx=22, pady=(16, 20))

    def _startup_install_plugin(self):
        """Ставит плагин в фоне (не блокирует окно)."""
        try:
            pok, pmsg = install_plugin(self.game)
            log(f"плагин при старте: {pmsg}")
            if not pok and "уже установлен" not in pmsg:
                self.after(0, lambda: self._set_status(f"Плагин: {pmsg}", "#e0a0a0"))
        except Exception:
            log_exc("_startup_install_plugin")

    def _animate_hero(self):
        """Чередует кадры баннера (красная/синяя мигалка) — эффект включённых огней."""
        try:
            if not self._frames:
                return
            self._frame_i = (self._frame_i + 1) % len(self._frames)
            self.hero.config(image=self._frames[self._frame_i])
            self.after(500, self._animate_hero)
        except Exception:
            pass

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

    def _update_status(self, text=None, fg=None, notes=None, btn_state=None, btn_text=None):
        if text is not None:
            self._upd_text = text
        if fg is not None:
            self._upd_fg = fg
        if notes is not None:
            self._upd_notes_text = notes
        if hasattr(self, "upd_label") and self.upd_label.winfo_exists():
            self.upd_label.config(text=self._upd_text, fg=self._upd_fg)
        if hasattr(self, "upd_notes") and self.upd_notes.winfo_exists():
            self.upd_notes.config(text=self._upd_notes_text)
        if hasattr(self, "upd_btn") and self.upd_btn.winfo_exists():
            if btn_state is not None:
                self.upd_btn.config(state=btn_state)
            if btn_text is not None:
                self.upd_btn.config(text=btn_text)

    def _refresh_agent_status(self, schedule=True):
        if getattr(self, "_closing", False):
            return
        running = is_agent_running()
        if hasattr(self, "agent_state"):
            self.agent_state.config(text="● включён" if running else "● выключен",
                                    fg=OKGRN if running else MUTED)
        if hasattr(self, "agent_btn"):
            self.agent_btn.config(text="Выключить агент" if running else "Включить агент")
        if hasattr(self, "nav_agent_state"):
            self.nav_agent_state.config(text="● агент: включён" if running else "● агент: выключен",
                                        fg=OKGRN if running else MUTED)
        if hasattr(self, "home_agent_state"):
            self.home_agent_state.config(text="● агент включён" if running else "● агент выключен",
                                         fg=OKGRN if running else MUTED)
        if schedule:
            self.after(4000, self._refresh_agent_status)

    def save_agent_close_pref(self):
        cfg = read_config()
        cfg["CLOSE_AGENT_WITH_LAUNCHER"] = "1" if self.close_agent_var.get() else "0"
        write_config(cfg)
        self._set_status("Агент будет закрываться вместе с лаунчером."
                         if self.close_agent_var.get()
                         else "Агент останется работать после закрытия лаунчера.",
                         "#98a1ac")

    def toggle_agent(self):
        if is_agent_running():
            ok, msg = stop_agent()
            self._set_status(msg, "#7fbf7f" if ok else "#e0a0a0")
        else:
            ok, msg = start_agent()
            self._set_status(msg, "#7fbf7f" if ok else "#e0a0a0")
        self._refresh_agent_status(schedule=False)

    def full_uninstall(self):
        if not messagebox.askyesno(
            APP_NAME,
            "Удалить LAPD-Records-Launcher с этого компьютера?\n\n"
            "Будут удалены лаунчер, агент, автозапуск, ярлыки, логи и локальные настройки.",
        ):
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Последнее подтверждение.\n\n"
            "После удаления лаунчер закроется. Чтобы вернуть его, нужно снова скачать установщик.",
        ):
            return
        ok, msg = uninstall_local_files(self.game)
        self._set_status(msg, "#7fbf7f" if ok else "#e0a0a0")
        if ok:
            messagebox.showinfo(APP_NAME, "Удаление запущено. Лаунчер сейчас закроется.")
            self._closing = True
            self.destroy()

    def on_close(self):
        self._closing = True
        try:
            self.save_agent_close_pref()
            if self.close_agent_var.get() and is_agent_running():
                ok, msg = stop_agent()
                log(f"закрытие лаунчера: {msg}", "INFO" if ok else "WARN")
        except Exception:
            log_exc("on_close")
        finally:
            self.destroy()

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
        self._button(btns, "Прикрепить скриншот", pick, CARD2, BORDER, small=True).pack(side="left")

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

    def support_chat(self):
        """Чат-поддержка: игрок пишет, лог прикладывается автоматически, видит ответы оператора."""
        dlg = tk.Toplevel(self)
        dlg.title("Поддержка LAPD")
        dlg.geometry("480x620")
        dlg.minsize(430, 500)
        dlg.configure(bg=BG)
        dlg.transient(self)

        state = {"ticket": None, "seen": 0, "att": None, "alive": True}

        def rph_log():
            p = os.path.join(self.game, "RagePluginHook.log") if self.game else None
            return p if (p and os.path.exists(p)) else None

        # ── ШАПКА ──
        top = tk.Frame(dlg, bg=CARD)
        top.pack(side="top", fill="x")
        tk.Label(top, text="● Поддержка LAPD", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(top, text="Опиши проблему — оператор ответит здесь. Лог игры приложится сам.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=440,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 12))

        # ── НИЗ: сначала прибиваем к низу, чтобы поле ввода всегда было видно ──
        send_row = tk.Frame(dlg, bg=BG)
        send_row.pack(side="bottom", fill="x", padx=14, pady=(4, 12))
        send_btn = self._button(send_row, "Отправить", lambda: send(), ACCENT, ACCENT2)
        send_btn.pack(side="right")
        inp_wrap = tk.Frame(send_row, bg=BORDER)
        inp_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))
        inp = tk.Entry(inp_wrap, bg=CARD2, fg=TEXT, insertbackground=ACCENT, relief="flat",
                       font=("Segoe UI", 11))
        inp.pack(fill="x", padx=1, pady=1, ipady=7)
        inp.bind("<Return>", lambda e: send())

        att_lbl = tk.Label(dlg, text="", bg=BG, fg=OKGRN, font=("Segoe UI", 8), anchor="w")
        att_lbl.pack(side="bottom", fill="x", padx=16)

        bar = tk.Frame(dlg, bg=BG)
        bar.pack(side="bottom", fill="x", padx=14, pady=(6, 2))

        # ── СЕРЕДИНА: лента сообщений ──
        box = tk.Frame(dlg, bg=BORDER)
        box.pack(side="top", fill="both", expand=True, padx=14, pady=(10, 6))
        msgs = tk.Text(box, bg=CARD, fg=TEXT, relief="flat", font=("Segoe UI", 10),
                       wrap="word", state="disabled", padx=10, pady=8, height=8)
        msgs.pack(fill="both", expand=True, padx=1, pady=1)
        msgs.tag_config("me", foreground="#4c8dff")
        msgs.tag_config("op", foreground="#3fb950")
        msgs.tag_config("sys", foreground=MUTED, font=("Segoe UI", 8))

        def add(text, tag):
            msgs.config(state="normal")
            msgs.insert("end", text + "\n\n", tag)
            msgs.config(state="disabled")
            msgs.see("end")

        def set_att(path):
            state["att"] = path
            if path:
                att_lbl.config(text="✓ приложится: " + os.path.basename(path), fg=OKGRN)
            else:
                att_lbl.config(text="")

        def toggle_log():
            if state["att"]:
                set_att(None)
            else:
                p = rph_log()
                if p:
                    set_att(p)
                else:
                    att_lbl.config(text="RagePluginHook.log не найден", fg=REDT)

        self._button(bar, "Приложить лог", toggle_log, CARD2, BORDER, small=True).pack(side="left")
        self._button(bar, "Закрыть обращение",
                     lambda: (sb_close_ticket(state["ticket"]) if state["ticket"] else None,
                              add("Обращение закрыто.", "sys")), CARD2, BORDER, small=True).pack(side="right")

        def _render_new(rows):
            for r in rows[state["seen"]:]:
                who = "Оператор" if r.get("from_admin") else "Вы"
                add(f"{who}: {r.get('body', '')}", "op" if r.get("from_admin") else "me")
                if r.get("attachment_url"):
                    add("вложение: " + r["attachment_url"], "sys")
            state["seen"] = len(rows)

        def poll():
            if not state["alive"]:
                return
            tid = state["ticket"]
            if not tid:
                dlg.after(8000, poll)
                return

            def work():
                try:
                    rows = sb_list_comments(tid)
                except Exception:
                    rows = None
                def render():
                    if not state["alive"]:
                        return
                    if rows is not None:
                        _render_new(rows)
                    dlg.after(8000, poll)
                dlg.after(0, render)
            threading.Thread(target=work, daemon=True).start()

        def load_history():
            try:
                tid = sb_open_ticket_id()
                rows = sb_list_comments(tid) if tid else []
            except Exception as e:
                dlg.after(0, lambda: add(f"Нет связи с поддержкой: {e}", "sys"))
                return

            def render():
                state["ticket"] = tid
                if tid:
                    _render_new(rows)
                else:
                    add("Опиши проблему и нажми «Отправить».", "sys")
                    if rph_log():
                        set_att(rph_log())   # сразу предлагаем передать лог
                        add("Лог RagePluginHook.log приложится к сообщению автоматически.", "sys")
                dlg.after(1500, poll)
            dlg.after(0, render)

        def send():
            text = inp.get().strip()
            if not text and not state["att"]:
                return
            inp.delete(0, "end")
            send_btn.config(state="disabled")
            att_path = state["att"]

            def work():
                try:
                    if not state["ticket"]:
                        state["ticket"] = sb_create_ticket(text or "Обращение")
                    att_url = None
                    if att_path:
                        data = open(att_path, "rb").read()
                        nm = f"{_client_id()}/{int(time.time())}_{os.path.basename(att_path)}"
                        att_url = sb_upload(nm, data, "text/plain")
                    sb_add_comment(state["ticket"], text or "(вложение)", att_url)
                    def done():
                        add(f"Вы: {text}" if text else "Вы: (вложение)", "me")
                        if att_url:
                            add("вложение: " + att_url, "sys")
                        set_att(None)
                        send_btn.config(state="normal")
                    dlg.after(0, done)
                except Exception as e:
                    dlg.after(0, lambda: (add(f"Не отправилось: {e}", "sys"),
                                          send_btn.config(state="normal")))
            threading.Thread(target=work, daemon=True).start()

        def on_close():
            state["alive"] = False
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", on_close)

        inp.focus_set()
        threading.Thread(target=load_history, daemon=True).start()

    def save_identity(self):
        cs = self.callsign.get().strip()
        nick = self.nickname.get().strip()
        if not cs or not nick:
            messagebox.showwarning(APP_NAME, "Заполни позывной и имя.")
            return
        cfg = read_config()
        cfg["CALLSIGN"], cfg["NICKNAME"] = cs, nick
        cfg.setdefault("UPLOAD_MODE", "github")
        cfg.setdefault("GITHUB_REPO", GITHUB_REPO)
        cfg.setdefault("WATCH_GAME", "1")
        cfg.setdefault("AUTO_PUBLISH", "0")
        cfg.setdefault("POLL_SECONDS", "8")
        # приём данных через шлюз (токена в клиенте нет). GATEWAY_URL/KEY вшиты при сборке.
        if GATEWAY_URL:
            cfg["GATEWAY_URL"] = GATEWAY_URL
            cfg["GATEWAY_KEY"] = GATEWAY_KEY
            cfg.pop("GITHUB_TOKEN", None)   # токен больше не нужен на клиенте
        elif "GITHUB_TOKEN" not in cfg:
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
        notes = m.get("notes", "")

        # ЛАУНЧЕР обновляем САМИ сразу: качаем, подменяем, перезапускаемся (без кнопки)
        if info.get("launcher_new"):
            self.after(0, lambda: self._update_status(
                text=f"⬇ обновляю лаунчер до {m.get('launcher')}…",
                fg="#e3b341", notes=notes, btn_state="disabled"))
            ok, msg = update_launcher(m)
            if ok and msg == "restart":
                self.after(0, lambda: (self._set_status(f"Обновлено до {m.get('launcher')} — перезапуск…", "#7fbf7f"),
                                       self.after(1000, self.destroy)))
                return
            # авто не вышло (напр. запуск из исходников) — попросим перезапустить
            self.after(0, lambda: self._update_status(
                text=f"● Обновление {m.get('launcher')} — перезапусти лаунчер", fg="#e3b341"))
            return

        # агент обновляем САМИ, тихо (безопасно, перезапуск не нужен)
        if info.get("agent_new"):
            self.after(0, lambda: self._update_status(text="⬇ обновляю агент…", fg="#e3b341"))
            ok, _ = update_agent(m)
            info["agent_new"] = not ok
            if ok:
                self.after(0, lambda: self._update_status(
                    text="✓ Агент обновлён автоматически.", fg=OKGRN, notes=notes))
                return

        self.after(0, lambda: self._update_status(
            text="✓ Установлена последняя версия.", fg=OKGRN,
            notes=("Что нового: " + notes) if notes else ""))

    def do_update(self):
        info = getattr(self, "_upd", None)
        if not info or not (info.get("launcher_new") or info.get("agent_new")):
            self._set_status("Обновлений нет.", "#98a1ac")
            return
        m = info["manifest"]
        self.upd_btn.config(state="disabled", text="Скачиваю…")
        prog = lambda p: self.after(0, lambda: self._update_status(text=f"Скачиваю… {int(p*100)}%"))

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
                self._update_status(text="Готово." if ok else "Ошибка обновления.",
                                    btn_state="normal", btn_text="Проверить обновления")
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def toggle_autostart(self):
        on = self.autostart_var.get()
        if set_autostart(on):
            self._set_status("Автозапуск включён — агент стартует с Windows и сам ловит игру."
                             if on else "Автозапуск выключен.",
                             "#7fbf7f" if on else "#98a1ac")
            self._refresh_agent_status(schedule=False)
        else:
            self._set_status("Не удалось изменить автозапуск.", "#e0a0a0")
            self.autostart_var.set(not on)

    def play(self):
        # 1) поставить плагин (лаунчер от админа — права есть).
        #    Плагин лежит в plugins\LSPDFR и грузится при ЛЮБОМ запуске игры.
        pok, pmsg = install_plugin(self.game)
        log(f"play: плагин — {pmsg}")
        # 2) запустить агент (синхронизация/публикация)
        aok, amsg = start_agent()
        self._refresh_agent_status(schedule=False)
        # 3) запустить игру через Vinewood (он поднимает игру со своими модами).
        #    Если Vinewood не найден — запасом напрямую через RagePluginHook.
        if start_vinewood():
            gok, gmsg = True, "запуск через Vinewood"
        else:
            gok, gmsg = launch_game(self.game)
        if gok:
            extra = "" if pok else f" (плагин: {pmsg})"
            self._set_status(f"Запускаю игру — {gmsg}. Плагин готов.{extra}", "#7fbf7f")
        else:
            self._set_status(f"Vinewood не найден и RagePluginHook тоже: {gmsg}. "
                             f"Агент: {amsg}.", "#e0a0a0")

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
