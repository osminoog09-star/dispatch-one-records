"""Small player-facing installer for LAPD-Records-Launcher.

The real launcher is still shipped as a PyInstaller onedir ZIP to avoid
the antivirus/temp-folder Python DLL issue. This bootstrapper is the single
file players download: it pulls the ZIP, installs it under LocalAppData,
creates shortcuts, and starts the launcher.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover - GUI fallback for broken Tk installs
    tk = None
    messagebox = None
    ttk = None


APP_NAME = "LAPD-Records-Launcher"
SETUP_TITLE = "LAPD-Records-Launcher Setup"
ZIP_URL = "https://github.com/osminoog09-star/dispatch-one-records/releases/latest/download/LAPD-Records-Launcher.zip"
INSTALL_BASE = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DispatchOne"
TARGET_DIR = INSTALL_BASE / "Launcher"
EXE_PATH = TARGET_DIR / f"{APP_NAME}.exe"
DOWNLOAD_DIR = INSTALL_BASE / "downloads"
SHORTCUT_NAME = f"{APP_NAME}.lnk"


def _startupinfo():
    if os.name != "nt":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return info


def _run_hidden(args: list[str]) -> None:
    subprocess.run(args, check=False, startupinfo=_startupinfo())


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_shortcut(path: Path, target: Path, workdir: Path) -> None:
    if os.name != "nt":
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$w=New-Object -ComObject WScript.Shell;"
        f"$s=$w.CreateShortcut({_ps_quote(str(path))});"
        f"$s.TargetPath={_ps_quote(str(target))};"
        f"$s.WorkingDirectory={_ps_quote(str(workdir))};"
        f"$s.IconLocation={_ps_quote(str(target))};"
        "$s.Save()"
    )
    _run_hidden(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])


def create_player_shortcuts() -> None:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / SHORTCUT_NAME
    start_menu = (Path(os.environ.get("APPDATA", str(Path.home()))) /
                  "Microsoft" / "Windows" / "Start Menu" / "Programs" / SHORTCUT_NAME)
    create_shortcut(desktop, EXE_PATH, TARGET_DIR)
    create_shortcut(start_menu, EXE_PATH, TARGET_DIR)


def close_running_launcher() -> None:
    if os.name == "nt":
        _run_hidden(["taskkill", "/F", "/IM", f"{APP_NAME}.exe"])


def download_zip(progress) -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DOWNLOAD_DIR / f"{APP_NAME}.zip"
    progress("Скачиваю актуальный лаунчер...", 12)

    request = urllib.request.Request(ZIP_URL, headers={"User-Agent": "LAPD-Records-Launcher-Setup"})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(zip_path, "wb") as fh:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = 12 + int(done * 48 / total)
                    progress(f"Скачиваю лаунчер... {done // 1024 // 1024} МБ", pct)

    if zip_path.stat().st_size < 1024 * 1024:
        raise RuntimeError("Скачанный файл слишком маленький. Проверь интернет и попробуй снова.")
    return zip_path


def extract_launcher(zip_path: Path, progress) -> Path:
    stage = Path(tempfile.mkdtemp(prefix="lapd_launcher_", dir=str(INSTALL_BASE)))
    progress("Распаковываю файлы лаунчера...", 68)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(stage)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    root = stage / APP_NAME
    if not (root / f"{APP_NAME}.exe").exists():
        root = stage
    if not (root / f"{APP_NAME}.exe").exists():
        shutil.rmtree(stage, ignore_errors=True)
        raise RuntimeError("В пакете не найден LAPD-Records-Launcher.exe.")
    return root


def copy_launcher(root: Path, progress) -> None:
    progress("Устанавливаю лаунчер...", 78)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root, TARGET_DIR, dirs_exist_ok=True)


def launch_installed() -> None:
    if EXE_PATH.exists():
        subprocess.Popen([str(EXE_PATH)], cwd=str(TARGET_DIR), startupinfo=_startupinfo())


def install(progress) -> None:
    INSTALL_BASE.mkdir(parents=True, exist_ok=True)
    zip_path = download_zip(progress)
    root = extract_launcher(zip_path, progress)
    try:
        close_running_launcher()
        copy_launcher(root, progress)
        progress("Создаю ярлыки...", 90)
        create_player_shortcuts()
    finally:
        shutil.rmtree(root.parent if root.name == APP_NAME else root, ignore_errors=True)

    progress("Готово. Запускаю лаунчер...", 100)
    launch_installed()


class InstallerApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(SETUP_TITLE)
        self.root.geometry("560x360")
        self.root.resizable(False, False)
        self.root.configure(bg="#07101d")

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor="#111c2b", background="#2f86ff",
                        bordercolor="#111c2b", lightcolor="#2f86ff", darkcolor="#2f86ff")

        frame = tk.Frame(self.root, bg="#07101d", padx=34, pady=30)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="LAPD Records", fg="#9fcbff", bg="#07101d",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(frame, text="Установщик лаунчера", fg="#f4f7fb", bg="#07101d",
                 font=("Segoe UI", 26, "bold")).pack(anchor="w", pady=(8, 6))
        tk.Label(frame, text=("Скачает актуальный LAPD-Records-Launcher, установит его в профиль Windows, "
                              "создаст ярлык и запустит лаунчер. ZIP вручную распаковывать не нужно."),
                 fg="#9aa7b8", bg="#07101d", justify="left", wraplength=480,
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 22))

        self.status = tk.Label(frame, text="Готов к установке.", fg="#dce7f7", bg="#07101d",
                               font=("Segoe UI", 11, "bold"))
        self.status.pack(anchor="w", pady=(0, 8))

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 24))

        buttons = tk.Frame(frame, bg="#07101d")
        buttons.pack(fill="x")
        self.install_button = tk.Button(buttons, text="Установить лаунчер", command=self.start,
                                        bg="#2f86ff", fg="white", activebackground="#1d6fe3",
                                        activeforeground="white", relief="flat", bd=0,
                                        padx=18, pady=11, font=("Segoe UI", 11, "bold"))
        self.install_button.pack(side="left")
        tk.Button(buttons, text="Закрыть", command=self.root.destroy,
                  bg="#152033", fg="#dce7f7", activebackground="#1c2b42",
                  activeforeground="white", relief="flat", bd=0, padx=18, pady=11,
                  font=("Segoe UI", 11, "bold")).pack(side="left", padx=(12, 0))

    def set_progress(self, text: str, value: int) -> None:
        self.root.after(0, lambda: self._set_progress(text, value))

    def _set_progress(self, text: str, value: int) -> None:
        self.status.configure(text=text)
        self.progress["value"] = value

    def start(self) -> None:
        self.install_button.configure(state="disabled")

        def worker() -> None:
            try:
                install(self.set_progress)
                self.root.after(0, lambda: messagebox.showinfo(SETUP_TITLE, "Готово. Лаунчер установлен и запущен."))
                self.root.after(800, self.root.destroy)
            except Exception as exc:
                self.root.after(0, lambda: self._fail(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _fail(self, exc: Exception) -> None:
        self.install_button.configure(state="normal")
        self.status.configure(text="Не удалось установить лаунчер.")
        messagebox.showerror(SETUP_TITLE, f"{exc}\n\nЗакрой лаунчер, проверь интернет и запусти установщик снова.")

    def run(self) -> None:
        self.root.mainloop()


def dry_run() -> None:
    print(json.dumps({
        "app": APP_NAME,
        "zip_url": ZIP_URL,
        "install_dir": str(TARGET_DIR),
        "exe": str(EXE_PATH),
        "installer_asset": f"{APP_NAME}-Setup.exe",
    }, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=SETUP_TITLE)
    parser.add_argument("--dry-run", action="store_true", help="Print installer configuration and exit.")
    args = parser.parse_args()
    if args.dry_run:
        dry_run()
        return 0
    if tk is None:
        install(lambda text, value: print(f"{value}% {text}"))
        return 0
    InstallerApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
