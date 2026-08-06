# Командный roadmap: Claude + Codex

Последнее обновление: 2026-08-07, Codex.

Цель: Codex и Claude могут работать параллельно, но не затирают файлы друг друга и не берут одну задачу дважды.

## Главное правило

Перед любой задачей:

1. Прочитать `WIP.md`, `HANDOFF.md`, `TECH_ROADMAP.md`, `ROADMAP_TEAM.md`.
2. Проверить `git status --short --branch`.
3. Если задача свободна, поставить WIP-lock.
4. Сделать маленький срез.
5. Проверить.
6. Обновить `WIP.md` и `HANDOFF.md`.
7. Commit + `git pull --rebase origin main` + push.

## Что нельзя

- Нельзя делать `git reset --hard`.
- Нельзя делать `git checkout .` или `git checkout -- .`.
- Нельзя делать общий `git stash`.
- Нельзя делать `git add -A` или `git add .`.
- Нельзя править `docs/` руками.
- Нельзя коммитить приватные файлы: `launcher/embedded_token.py`, `launcher/gateway_config.py`, приватные токены и webhook URL.

## Зоны Codex

Codex ведёт:

- `launcher/**`
- `agent/**`
- `dispatch-plugin/**`, если задача про сбор данных из игры
- `server/app/db.py`
- `server/app/main.py`
- `server/discord_post.py`
- `server/export_static.py`, если меняется экспорт
- `server/import_inbox.py`
- `publish.py`
- `supabase/*.sql`
- `gateway/worker.js`
- `server/app/static/supa.js`
- inline `<script>` в `tickets.html`, `staff.html`, `dictionaries.html`, `admin.html`
- `version.json`
- GitHub release assets
- технические roadmap/handoff/WIP документы

Codex может трогать визуал сайта только если задача явно про регрессию, ссылки, локализацию данных или безопасный QA.

## Зоны Claude

Claude ведёт:

- `server/app/templates/*.html`, кроме опасных inline Supabase-скриптов
- `server/app/static/style.css`
- визуальный polish сайта
- тексты страниц
- пустые состояния
- адаптивность
- внешний вид карты
- UI-макеты новых страниц без изменения backend/API
- QA видимых страниц: русский текст, обрезания, английские хвосты, странные пустые блоки

Claude не трогает лаунчер, агент, SQL, Supabase JS, backend и release assets без явной передачи задачи.

## Общие файлы

Общие файлы можно править обоим, но только свои строки и только с понятной записью:

- `WIP.md`
- `HANDOFF.md`
- `TECH_ROADMAP.md`
- `PLAYER_ROADMAP.md`
- `PLAYER_UPDATES.md`
- `ROADMAP_TEAM.md`
- `CLAUDE_QA_NOTES.md`
- `SITE_QA_*.md`

## JS-зависимые классы

Можно стилизовать, нельзя удалять или переименовывать:

- `sb-edit`
- `sb-badge`
- `sb-rank`
- `sb-dept`
- `nav-drop`
- `nav-menu`
- `admin-only`
- `auth-slot`
- `tk-*`
- `dic-*`
- `.empty`
- `.empty-sub`

## Текущая очередь

### Срез 1: связанные карточки

Ведущий: Codex, потому что нужны backend-связи и проверка ссылок.

Файлы:

- `server/app/db.py`
- `server/app/main.py`
- шаблоны точечно, если нужны блоки ссылок
- `server/export_static.py`, если нужно добавить статические маршруты
- `docs/` только через экспорт

Результат:

- из ареста, вызова, штрафа, суда, офицера и досье можно открыть связанные записи;
- все ссылки проходят static link check.

### Срез 2: статистика периодов

Ведущий: Codex для данных, Claude для визуала.

Файлы Codex:

- `server/app/db.py`
- `server/app/main.py`

Файлы Claude:

- шаблоны и CSS карточек статистики

Результат:

- 24 часа, 7 дней, 30 дней;
- аресты, штрафы, вызовы, суды, смены, часы, районы.

### Срез 3: смены и Discord

Ведущий: Codex.

Файлы:

- `agent/**`
- `server/app/db.py`
- `server/discord_post.py`
- `publish.py`

Результат:

- понятный итог смены;
- отчёт уходит в Discord;
- нет дублей при повторном импорте.

### Срез 4: карта и координаты

Ведущие: Codex + Claude.

Codex:

- сбор/хранение координат;
- ссылки `/map?zone=...`, позже `/map?x=...&y=...`.

Claude:

- внешний вид карты;
- адаптивность;
- подписи и легенда.

### Срез 5: поддержка и диагностика

Ведущий: Codex для правил и безопасности, Claude для UI.

Результат:

- диагностика логов без AI;
- создание тикета с краткой сводкой;
- позже AI только как второй уровень.

### Срез 6: роли и модерация

Ведущий: Codex.

Результат:

- `owner`, `admin`, `moderator`, `helper`, `viewer`;
- аудит действий;
- защита владельца.

### Срез 7: live-агент

Ведущий: Codex.

Результат:

- агент отправляет изменения во время игры;
- нет дублей;
- понятный статус последней отправки.

## Проверки перед коммитом

Для Python:

```powershell
python -m py_compile server/app/db.py server/app/main.py server/app/discord_post.py server/export_static.py agent/pdcomp_sync.py
```

Для сайта:

```powershell
python server/export_static.py
```

Для лаунчера:

```powershell
python -m py_compile launcher/launcher.py launcher/setup_installer.py
```

Для видимых страниц:

- основные маршруты отдают 200;
- внутренние ссылки в `docs/` не битые;
- нет явных английских хвостов в видимом HTML;
- нет обрезанного текста на скриншотах/ручной проверке.

## Если задача не завершена

Оставить в `WIP.md`:

```text
- PAUSED 2026-08-07 AgentName: что сделано, что осталось, какие файлы затронуты, какие проверки уже прошли.
```

Не оставлять активный замок без пояснения.
