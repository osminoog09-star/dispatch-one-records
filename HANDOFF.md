# LAPD Records handoff

Последнее обновление: 2026-08-07, Codex.

## Текущее состояние

- Рабочая ветка: `main`.
- Публичный сайт собирается из Flask-шаблонов командой `python server/export_static.py` в `docs/`.
- `docs/` не редактировать руками.
- Публичная установка лаунчера должна идти через один файл `LAPD-Records-Launcher-Setup.exe`.
- `version.json.launcher_url` оставлять на `LAPD-Records-Launcher.zip`: это внутренний onedir-пакет для установщика и автообновления, не основная ссылка для игроков.
- Приватные файлы `launcher/embedded_token.py`, `launcher/gateway_config.py`, `launcher/pdcomp_sync.exe` не коммитить.

## Codex note 2026-08-07

Лаунчер обновлён до `1.4.13`.

Что исправлено:

- Убрано обрезание текста в разделах лаунчера.
- Окно теперь шире (`860px`) и может растягиваться, минимальная высота поднята до `700px`.
- Левый блок статуса больше не режется снизу: статус игры и агента вынесен в нижнюю часть бокового меню.
- Раздел `Инструкция / Как это работает` переведён с обычного `Label` на прокручиваемый `Text` с внутренними отступами, чтобы первые буквы строк не съедались.
- Онбординг первого запуска тоже переведён на безопасный текстовый блок.
- Все старые `wraplength=500/510` заменены на общий `CONTENT_WRAP`.
- Баннеры `launcher/banner_red.png` и `launcher/banner_blue.png` перерисованы в размере `860x190`: LAPD shield, MDT-сетка, красно-синие мигалки, статус игры и агент. Визуально проверено, обрезанных букв нет.
- Найдена битая кириллица в служебных файлах (`version.json`, `WIP.md`, `HANDOFF.md`, `PLAYER_UPDATES.md`, `launcher/BUILD.md`), эти файлы переписаны нормальным UTF-8.

Проверки для этого среза:

```powershell
python -m py_compile launcher/launcher.py launcher/setup_installer.py
rg -n 'wraplength=500|wraplength=510|geometry\("760|resizable\(False' launcher/launcher.py
```

После правок нужно пересобирать onedir-пакет и обновлять release asset `LAPD-Records-Launcher.zip`.

## Важные правила для следующего агента

- Не делать `git reset --hard`, `git checkout .`, `git stash` на всём дереве.
- Стейджить только свои файлы явными путями.
- Перед push: `git pull --rebase origin main`.
- Если трогаешь шаблоны сайта или `server/app/static/style.css`, после этого запускать `python server/export_static.py`.
- Если трогаешь лаунчер, после этого запускать `python -m py_compile launcher/launcher.py launcher/setup_installer.py` и проверять UI глазами.
- Если трогаешь релиз лаунчера, обновлять `version.json`, `PLAYER_UPDATES.md`, `HANDOFF.md`, release asset и страницу `/launcher`.

## Быстрая проверка сайта

```powershell
python -m py_compile server/app/db.py server/app/main.py server/app/discord_post.py agent/pdcomp_sync.py server/export_static.py
python server/export_static.py
python -c "import sys; sys.path.insert(0,'server'); from app.main import app; c=app.test_client(); paths=['/','/cases','/case/19','/citations','/citation/7','/court','/court/20','/files','/file/Eddie%20Thomas','/officer/7-WILLIAM-1','/shifts','/shift/10','/map','/register','/staff','/tickets','/dictionaries','/callouts','/callout/7','/launcher']; [print(p, c.get(p).status_code) for p in paths]"
rg -n "Wobbler|arrested|CITATIONS|RECORDS|COURT|Courtroom|Court-Appointed|CJA Panel" docs -g "*.html"
```

## Сборка лаунчера

Подробная команда лежит в `launcher/BUILD.md`.

Коротко:

- `LAPD-Records-Launcher-Setup.exe` — один файл для игроков.
- `LAPD-Records-Launcher.zip` — внутренний onedir-пакет для установщика и автообновления.
- Не путать эти ссылки в `version.json`.

## Следующий хороший срез

Полный визуальный QA сайта:

- проверить обрезанный текст на всех основных страницах;
- проверить связанные ссылки между делами, вызовами, судами, офицерами, досье и картой;
- проверить пустые состояния, чтобы они объясняли игроку, почему данных нет;
- проверить, что все публичные кнопки скачивания ведут на `LAPD-Records-Launcher-Setup.exe`, а не на ZIP.
