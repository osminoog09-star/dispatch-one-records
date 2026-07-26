"""
Dispatch One — установщик для игроков.
Ставит агент синхронизации, настраивает профиль (позывной/имя/Discord),
прописывает позывной в игре, создаёт ярлык и автозапуск.
"""
import os
import shutil
import sys
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "Dispatch One"
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "DispatchOne")
SITE_URL_DEFAULT = "https://osminoog09-star.github.io/dispatch-one-records/"
GITHUB_REPO = "osminoog09-star/dispatch-one-records"
AGENT_EXE = "pdcomp_sync.exe"


def get_embedded_token():
    """Ключ подключения, вшитый при сборке (в исходниках его нет)."""
    try:
        import embedded_token
        return embedded_token.get_token()
    except Exception:
        return ""


def resource(name):
    """Файл, вшитый в установщик (PyInstaller) или лежащий рядом."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def find_game():
    candidates = [
        r"C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy",
        r"C:\Program Files\Rockstar Games\Grand Theft Auto V",
        r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V",
        r"D:\Games\Grand Theft Auto V",
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "plugins", "LSPDFR", "pdComp")):
            return c
    return None


def write_config(path, values):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Настройки Dispatch One (создано установщиком)\n")
        for k, v in values.items():
            f.write(f"{k}={v}\n")


def set_ini_value(path, key, value, section=None):
    if not os.path.exists(path):
        return False
    import re
    try:
        lines = open(path, "r", encoding="utf-8-sig").read().splitlines()
    except Exception:
        return False
    out, cur, changed = [], "", False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1].strip().lower()
            out.append(line)
            continue
        m = re.match(r"^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$", line)
        if m and m.group(2).lower() == key.lower() and (section is None or cur == section.lower()):
            new = f"{m.group(1)}{m.group(2)}{m.group(3)}{value}"
            changed = changed or new != line
            out.append(new)
        else:
            out.append(line)
    if changed:
        try:
            open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
        except Exception:
            return False
    return changed


def apply_callsign(game_dir, callsign, nickname):
    base = os.path.join(game_dir, "plugins", "LSPDFR")
    ok = []
    for path, key, sec in [
        (os.path.join(base, "GrammarPolice", "custom.ini"), "Callsign", None),
        (os.path.join(base, "CalloutInterface.ini"), "MDTCallsign", None),
        (os.path.join(base, "BlueLineScanner.ini"), "VizLabel", None),
        (os.path.join(base, "pdComp", "config.ini"), "Callsign", "Officer"),
    ]:
        if set_ini_value(path, key, callsign, sec):
            ok.append(os.path.basename(path))
    if nickname:
        set_ini_value(os.path.join(base, "pdComp", "config.ini"), "Name", nickname, "Officer")
    return ok


def make_shortcut(target, link_path, workdir):
    try:
        import subprocess
        ps = (f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{link_path}');"
              f"$s.TargetPath='{target}';$s.WorkingDirectory='{workdir}';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=20)
        return os.path.exists(link_path)
    except Exception:
        return False


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — установка")
        self.geometry("520x700")
        self.minsize(520, 620)
        self.resizable(False, True)
        self.configure(bg="#12151a")
        # окно с правами админа часто открывается позади — выводим вперёд
        self.after(80, self._bring_to_front)

        # ---- кнопка внизу: крепим ПЕРВОЙ, чтобы её никогда не срезало ----
        bottom = tk.Frame(self, bg="#12151a")
        bottom.pack(side="bottom", fill="x", pady=(6, 16))
        tk.Button(bottom, text="Установить", command=self.install,
                  bg="#3b82f6", fg="white", font=("Segoe UI", 12, "bold"),
                  relief="flat", padx=30, pady=11, cursor="hand2").pack()
        self.status = tk.Label(bottom, text="", bg="#12151a", fg="#98a1ac",
                               font=("Segoe UI", 9))
        self.status.pack(pady=(8, 0))

        self._label("Dispatch One", 18, "#e8ecf1").pack(pady=(20, 2))
        self._label("Синхронизация игры с сайтом сообщества", 10, "#98a1ac").pack()

        frm = tk.Frame(self, bg="#12151a")
        frm.pack(fill="x", padx=36, pady=14)

        self.callsign = self._field(frm, "Позывной", "например, 1-ADAM-12")
        self.nickname = self._field(frm, "Имя персонажа", "например, John Miller")
        self.discord = self._field(frm, "Discord (обязательно)", "ваш ник в Discord")
        tk.Label(frm, text="Больше ничего вводить не нужно — подключение к сайту\n"
                           "департамента уже настроено.",
                 bg="#12151a", fg="#6b7684", font=("Segoe UI", 8), wraplength=440,
                 justify="left").pack(anchor="w", pady=(10, 0))

        self.autostart = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Запускать вместе с Windows", variable=self.autostart,
                       bg="#12151a", fg="#98a1ac", selectcolor="#1b2027",
                       activebackground="#12151a", activeforeground="#e8ecf1",
                       font=("Segoe UI", 9)).pack(anchor="w", padx=36)

    def _bring_to_front(self):
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(600, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _label(self, text, size, color):
        return tk.Label(self, text=text, bg="#12151a", fg=color,
                        font=("Segoe UI", size, "bold" if size > 12 else "normal"))

    def _field(self, parent, label, placeholder, default=""):
        tk.Label(parent, text=label, bg="#12151a", fg="#98a1ac",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 2))
        e = tk.Entry(parent, bg="#1b2027", fg="#e8ecf1", insertbackground="#e8ecf1",
                     relief="flat", font=("Segoe UI", 10))
        e.pack(fill="x", ipady=6)
        if default:
            e.insert(0, default)
        e.placeholder = placeholder
        return e

    def install(self):
        cs = self.callsign.get().strip()
        nick = self.nickname.get().strip()
        dis = self.discord.get().strip()
        if not cs or not nick or not dis:
            messagebox.showwarning(APP_NAME, "Заполни позывной, имя персонажа и Discord.")
            return

        key = get_embedded_token()
        if not key:
            messagebox.showerror(
                APP_NAME,
                "В установщике нет ключа подключения.\n\n"
                "Скачай установщик заново с сайта департамента.")
            return

        try:
            os.makedirs(INSTALL_DIR, exist_ok=True)
            src = resource(AGENT_EXE)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(INSTALL_DIR, AGENT_EXE))

            game = find_game()
            store = (os.path.join(game, "plugins", "LSPDFR", "pdComp", "data", "store")
                     if game else "")
            write_config(os.path.join(INSTALL_DIR, "sync-config.ini"), {
                # данные уходят прямо в GitHub — свой сервер не нужен
                "UPLOAD_MODE": "github",
                "GITHUB_REPO": GITHUB_REPO,
                "GITHUB_TOKEN": key,
                "CALLSIGN": cs,
                "NICKNAME": nick,
                "DISCORD": dis,
                "WATCH_GAME": "1",      # работать только во время игры
                "AUTO_PUBLISH": "0",    # сборку сайта делает GitHub
                "POLL_SECONDS": "8",
                **({"PDCOMP_STORE": store} if store else {}),
            })

            applied = apply_callsign(game, cs, nick) if game else []

            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            make_shortcut(os.path.join(INSTALL_DIR, AGENT_EXE),
                          os.path.join(desktop, "Dispatch One.lnk"), INSTALL_DIR)

            if self.autostart.get():
                startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                       "Start Menu", "Programs", "Startup")
                if os.path.isdir(startup):
                    make_shortcut(os.path.join(INSTALL_DIR, AGENT_EXE),
                                  os.path.join(startup, "Dispatch One.lnk"), INSTALL_DIR)

            msg = f"Установлено в:\n{INSTALL_DIR}\n\n"
            msg += f"Игра найдена: {game}\n" if game else "Игра не найдена — путь задай в sync-config.ini\n"
            msg += (f"Позывной прописан в: {', '.join(applied)}\n" if applied
                    else "Позывной в игре не изменён (запусти установщик от админа)\n")
            msg += "\nЯрлык на рабочем столе создан."
            messagebox.showinfo(APP_NAME, msg)
            self.destroy()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Ошибка установки:\n{e}")


if __name__ == "__main__":
    Installer().mainloop()
