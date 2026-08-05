# Сборка лаунчера

Лаунчер теперь использует два баннера:

- `banner_red.png`
- `banner_blue.png`

Их нужно либо вшить в PyInstaller, либо положить рядом с новым `LAPD-Records-Launcher.exe`.

Важно: предыдущая сборка включала приватные модули `embedded_token.py` и `gateway_config.py`.
Не пересобирай релизный `.exe`, если этих файлов нет рядом с `launcher.py`, иначе лаунчер может потерять доступ к шлюзу/токену.

Пример команды для релизной сборки, когда приватные файлы на месте:

```powershell
py -m PyInstaller --onefile --windowed --name LAPD-Records-Launcher --distpath launcher/dist --workpath launcher/build --specpath launcher/build --add-data "launcher/banner_red.png;." --add-data "launcher/banner_blue.png;." --add-data "launcher/DispatchOne.MDT.dll;." --add-binary "agent/dist/pdcomp_sync.exe;." --hidden-import embedded_token --hidden-import gateway_config launcher/launcher.py
```

После сборки проверь:

```powershell
python -m py_compile launcher/launcher.py
```

И глазами открой `launcher/dist/LAPD-Records-Launcher.exe`: сверху должен быть баннер LAPD с красно-синим эффектом мигалок.
