# LAPD Records handoff

Последнее обновление: 2026-08-13, Claude.

## Claude note 2026-08-13 (вечер): единый источник званий + полный QA

**Звания/отделы теперь только в Supabase.** Раньше они лежали в ДВУХ местах и разошлись:
главная рендерила из SQLite (`o.rank_label` / `o.department_label` → «Detective I / Patrol
Division»), а админка и `/staff` писали в Supabase `officer_profiles` («Sergeant II», отдел
пуст) — пользователь видел разные звания на разных страницах. Сделано:
- главная, профиль офицера и персонал показывают плейсхолдер `.sb-rankdept[data-cs]`,
  который заполняется из Supabase; общий скрипт лежит в конце `base.html` (там же рендер
  ролевых бейджей `.sb-role[data-discord]`);
- из `staff.html` убраны локальные SQLite-селекты звания/отдела и чекбокс «админ», иначе
  это второй источник, не попадающий на публичный сайт;
- справочники в Supabase русифицированы, добавлен отдел «Управление LAPD» (командные
  звания привязаны к нему).
**Правило: не возвращать `rank_label`/`department_label` в шаблоны — это второй источник.**

**Проверка сайта одной командой:** `py server/qa_check.py`. Проверяет маршруты (все 167,
включая каждое дело/офицера/досье), битые ссылки и мусор в `docs/`, дубли и сирот в базе,
отсутствие второго источника званий и живость Supabase-эндпоинтов. Возвращает код 1 при
провале. Прогонять после каждого заметного изменения — обычная проверка «страница отдаёт
200» рассогласование данных не ловит.

## Claude note 2026-08-13

### Supabase: роли и модерация теперь ПРИМЕНЕНЫ в проде

Важно для следующего агента: раньше `supabase/admin_roles.sql` никогда не выполнялся на живой
базе, а таблица `admins` была пуста — то есть `current_admin_role()` у всех возвращал `viewer`
и админка фактически не работала. Теперь применены `admin_roles.sql`, `moderation.sql`,
`admin_grant.sql`; владелец — `osminoog09@gmail.com` (role `owner`, protected).

Модерация офицеров работает без правки `roster.json`:
- `/admin` → раздел «Модерация»: список ждущих, кнопки Одобрить/Отклонить, ручное одобрение
  по позывному и тумблер «Авто-одобрение» (таблицы `roster`, `pending_officers`, `moderation`).
- `server/import_inbox.py` читает одобренных и флаг авто-режима из Supabase, неодобренных
  отправляет в `pending_officers` через `report_pending`, а на каждом прогоне сам возвращает
  из `server/inbox/pending/` тех, кого одобрили. Публикация идёт существующим cron `*/30`.
- Проверено в бою: одобрение 7-ADAM-20 → Actions опубликовал его 9 смен; 7-ADAM-1 приехал
  на модерацию автоматически.
- Фолбэк цел: если Supabase недоступен, импорт работает по `roster.json`.

Выдача доступов: в «Команде доступа» теперь выпадающий список всех, кто входил через Discord
(`list_site_users`), выдача по `user_id` с автоподстановкой email (`set_admin_role_by_id`).
На карточках офицеров статичный бейдж «админ» заменён живым бейджем роли по Discord-нику
(`public_staff_roles`, доступна анониму — работает на статичном сайте).

### Двоение записей устранено

Все 18 «вызовов» в базе — CAD-зеркала задержаний (`external_id LIKE 'case-callout:%'`),
настоящих вызовов игра не отдаёт. Они дублировали аресты в хронологии личного дела, в секции
«Вызовы» на странице офицера и в счётчике `subject_intel`. Добавлен `db.MIRROR_CALLOUT` и
флаг `real_only` у `list_callouts`/`callouts_count`. Журнал `/callouts` намеренно оставлен на
зеркалах (иначе он пустой), там добавлено пояснение. **Не возвращать зеркала в списки рядом
с задержаниями.**

### Плагин и агент

Плагин `DispatchOne.MDT` не грузился у игроков: наследовался от `Rage.Plugin`, который в
реальном RagePluginHook `sealed` (правильная база — `LSPD_First_Response.Mod.API.Plugin` +
`[assembly: Rage.Attributes.Plugin(...)]`), затем падал `PluginFolder()` — LSPDFR грузит
плагины из памяти, поэтому `Assembly.Location` пуст. Агент искал pdComp по жёсткому пути
`C:\Program Files\...`, из-за чего у игроков с игрой на другом диске (Steam на `F:`) аресты
и штрафы не собирались вовсе — добавлен авто-поиск. Выпущено launcher 1.4.16 + agent 1.1.2,
ассеты залиты в релиз. У игроков «дел 0» пропадёт после обновления агента.

## Текущее состояние

- Рабочая ветка: `main`.
- Публичный сайт собирается из Flask-шаблонов командой `python server/export_static.py` в `docs/`.
- `docs/` не редактировать руками.
- Публичная установка лаунчера должна идти через один файл `LAPD-Records-Launcher-Setup.exe`.
- `version.json.launcher_url` оставлять на `LAPD-Records-Launcher.zip`: это внутренний onedir-пакет для установщика и автообновления, не основная ссылка для игроков.
- Приватные файлы `launcher/embedded_token.py`, `launcher/gateway_config.py`, `launcher/pdcomp_sync.exe` не коммитить.

## Codex note 2026-08-07

### Player-facing launcher news

Добавлена публичная новость о новом лаунчере:

- Главная страница получила блок “Новости LAPD Records” с кнопками на скачивание лаунчера и поддержку.
- Страница `/launcher` получила блок “Актуальное обновление” с короткими шагами: скачать `LAPD-Records-Launcher-Setup.exe`, войти через Discord, при ошибках создать тикет с логом.
- `version.json.notes` обновлён человеческим текстом для блока “Что нового” внутри лаунчера.
- `docs/` пересобран через `python server/export_static.py`.

### Unified Discord account for site and launcher

Добавлен первый срез единого аккаунта без возврата Discord-бота тикетов:

- Сайт получил маршрут `/launcher-login` и шаблон `server/app/templates/launcher_login.html`.
- Лаунчер открывает `/launcher-login/?port=...&state=...`; сайт выполняет обычный Supabase OAuth через Discord и возвращает сессию на локальный `http://127.0.0.1:<port>/callback`.
- В `launcher/launcher.py` добавлены хранение `AUTH_ACCESS_TOKEN`, `AUTH_REFRESH_TOKEN`, `AUTH_USER_ID`, Discord-имени/email и кнопки “Войти через Discord” / “Выйти” в разделе “Профиль”.
- Supabase REST/Storage запросы лаунчера используют user access token, если он живой; старый `x-client-id` сохранён как fallback для уже созданных тикетов.
- `/support` на сайте теперь пишет `user_id` в тикеты/комментарии, если пользователь вошёл через Discord, и читает обращения по `client_id` или `user_id`.
- `supabase/chat.sql` и `supabase/unified_tickets.sql` добавляют `user_id` и RLS-чтение `user_id = auth.uid()`.

Продовая Supabase уже обновлена: 2026-08-07 Codex прогнал `supabase/unified_tickets.sql` в SQL Editor проекта `gwvqfiwdbviwoimvhdvg`, результат `Success. No rows returned`. Общий Discord-аккаунт сайта и лаунчера теперь может связывать тикеты через `user_id`; старый `client_id` остаётся fallback для старых/анонимных обращений.

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

Продовая Supabase уже обновлена: 2026-08-07 Codex прогнал `supabase/unified_tickets.sql` в SQL Editor проекта `gwvqfiwdbviwoimvhdvg`, результат `Success. No rows returned`. Сайт/лаунчер всё равно сохраняют fallback по `client_id` для старых тикетов и анонимных обращений.

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
