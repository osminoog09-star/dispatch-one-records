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

### Unified support tickets

Сделан безопасный срез единой поддержки без Discord-бота:

- Добавлен маршрут `/support` и шаблон `server/app/templates/support.html`.
- На сайте появилась публичная форма обращения без входа; игрок видит свои тикеты по стабильному `client_id` браузера.
- `server/app/static/supa.js` теперь создаёт `lapd_support_client_id` в `localStorage` и отправляет его в Supabase как `x-client-id`.
- Админский `/tickets` показывает источник обращения: сайт или лаунчер; статусы отображаются по-русски.
- Лаунчер при создании тикета пишет `source = launcher`, но имеет fallback для старой базы без новых колонок.
- Добавлена миграция `supabase/unified_tickets.sql`: поля `source`, `last_message_at`, `closed_at`, таблица `ticket_attachments`, индексы и триггеры. Discord-поля в миграции остаются как совместимость, но активная схема их не использует.
- `/support` делает локальную rule-based диагностику `.log/.txt`; в Supabase уходит только краткая сводка, не весь лог.
- По решению пользователя удалены `discord_ticket_bot/` и `DISCORD_TICKETS.md`: тикеты ведём без отдельного Discord-бота и без webhook-секретов.
- `docs/` пересобран через `python server/export_static.py`, `/support` отдаёт 200.

Важно: чтобы новые поля заработали в проде, прогнать в Supabase SQL Editor файл `supabase/unified_tickets.sql`. До этого сайт/лаунчер имеют fallback для старой базы.

Следующий Codex-срез по поддержке: вложения сайта через storage bucket `support`, фильтры открытые/закрытые/источник/приоритет, назначение ответственного helper/moderator и быстрые шаблоны ответов.

### Support tickets without Discord

Пользователь отменил Discord-каналы тикетов. Не возвращать `discord_ticket_bot/` без отдельного подтверждения. Рабочая схема сейчас такая: сайт `/support` + лаунчер `support_chat` + админская очередь `/tickets`.

### Roadmap cleanup

Roadmap-документы синхронизированы:

- `PLAYER_ROADMAP.md` переписан как понятный план для игроков без технического мусора.
- `TECH_ROADMAP.md` переписан как рабочая очередь разработки с критериями готовности.
- `ROADMAP_TEAM.md` обновлён под текущие зоны ответственности Codex/Claude.
- `WIP.md` приведён к той же очереди задач.
- `PLAYER_UPDATES.md` получил короткую заметку для игроков про порядок ближайших обновлений.

Текущий порядок работ:

1. Связанные карточки везде.
2. Статистика 24 часа / 7 дней / 30 дней.
3. Смены и Discord-отчёты.
4. Карта и координаты.
5. Поддержка и диагностика логов.
6. Админка, модерация и роли.
7. Live-синхронизация агента.

После этого среза следующий исполнитель должен брать пункт 1: связанные карточки.

### Site QA

Сделан первый полный QA-срез сайта:

- В `server/app/db.py` расширена локализация судебных данных pdComp.
- Убраны видимые английские хвосты из судебных карточек и связанных личных дел: `Private Counsel`, `Self-Represented`, `No contest`, `Fix-It`, `Fine paid`, `United States v.`, `Probation terms`, `Appeal denied` и похожие.
- Хронология личных дел теперь локализует связанные судебные поля до вывода.
- `docs/` пересобран через `python server/export_static.py`.
- Проверки: py_compile прошёл, 24 ключевых Flask-маршрута отдают `200`, внутренних битых ссылок в `docs/` — 0, целевых английских хвостов в видимом HTML — 0.
- Детали в `SITE_QA_2026-08-07.md`.

Следующий продуктовый шаг: связанные карточки и статистика. Пользователь хочет открывать из любого места связанные аресты, вызовы, суды, штрафы, карту и хронологию; также нужны срезы статистики за 24 часа / неделю / месяц и отчёты 12-часовых смен.

### Launcher

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
