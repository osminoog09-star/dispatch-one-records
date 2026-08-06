# Сборка лаунчера

Лаунчер собирается в режиме `--onedir`, а не `--onefile`.

Почему так:

- `--onefile` распаковывает `python314.dll` во временную папку `_MEI...`;
- у игроков антивирус или очистка temp иногда удаляет DLL до запуска;
- появляется ошибка `Failed to load Python DLL ... _MEI...\\python314.dll`;
- `--onedir` кладёт Python DLL рядом с `LAPD-Records-Launcher.exe`, поэтому temp не используется.

## Приватные файлы

Перед релизной сборкой рядом с `launcher.py` должны быть локальные приватные файлы:

- `embedded_token.py`
- `gateway_config.py`
- `pdcomp_sync.exe`

Их нельзя коммитить. Если их нет, релизный лаунчер потеряет токен/шлюз/агент.

## Команда сборки

```powershell
py -m PyInstaller --onedir --windowed --name LAPD-Records-Launcher --distpath launcher/dist --workpath launcher/build --specpath launcher/build --add-data "launcher/banner_red.png;." --add-data "launcher/banner_blue.png;." --add-data "launcher/DispatchOne.MDT.dll;." --add-binary "launcher/pdcomp_sync.exe;." --hidden-import embedded_token --hidden-import gateway_config launcher/launcher.py
```

Результат:

- папка `launcher/dist/LAPD-Records-Launcher/`;
- главный файл `launcher/dist/LAPD-Records-Launcher/LAPD-Records-Launcher.exe`;
- рядом папка `_internal` с Python DLL и зависимостями.

## Архив для релиза

GitHub Release должен получать архив для внутреннего автообновления лаунчера:

```powershell
Compress-Archive -Path launcher/dist/LAPD-Records-Launcher/* -DestinationPath launcher/dist/LAPD-Records-Launcher.zip -Force
```

В `version.json` `launcher_url` должен указывать на:

```text
https://github.com/osminoog09-star/dispatch-one-records/releases/latest/download/LAPD-Records-Launcher.zip
```

Это технический пакет. Его не нужно давать игрокам как основной способ установки.

## Один установщик для игроков

Для сайта и Discord нужен отдельный файл:

```text
LAPD-Records-Launcher-Setup.exe
```

Он скачивает архив лаунчера сам, устанавливает его в:

```text
%LOCALAPPDATA%\DispatchOne\Launcher
```

создаёт ярлыки и запускает `LAPD-Records-Launcher.exe`.

Сборка установщика:

```powershell
python -m py_compile launcher/setup_installer.py
py -m PyInstaller --onefile --windowed --name LAPD-Records-Launcher-Setup --distpath launcher/dist --workpath launcher/build/setup --specpath launcher/build --clean launcher/setup_installer.py
```

В `version.json` `installer_url` должен указывать на:

```text
https://github.com/osminoog09-star/dispatch-one-records/releases/latest/download/LAPD-Records-Launcher-Setup.exe
```

Публичная страница `/launcher` и регистрация должны вести именно на `installer_url`,
а не на `launcher_url`.

## Проверка

```powershell
python -m py_compile launcher/launcher.py launcher/setup_installer.py
python launcher/setup_installer.py --dry-run
```

Затем открыть:

```powershell
launcher/dist/LAPD-Records-Launcher/LAPD-Records-Launcher.exe
```

Проверить глазами:

- сверху баннер LAPD с красно-синим эффектом мигалок;
- слева разделы `Главная`, `Профиль`, `Агент`, `Поддержка`, `Настройки`, `Инструкция`;
- первый запуск показывает окно `Добро пожаловать`;
- кнопка `ИГРАТЬ`, чат поддержки, агент и логи работают.
