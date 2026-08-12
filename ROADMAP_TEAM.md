# Кто что делает: Claude + Codex

Правила работы (git, проверки, запреты) — в `AGENTS.md`, здесь только распределение.

Обновлено: 2026-08-13.

## Принцип

Не сидим вдвоём на одной задаче и в одном файле. Берём **разные** задачи по очереди, каждый —
то, что делает лучше.

1. У каждого агента максимум **одна** активная задача (замок в `WIP.md`).
2. Закончил — берёшь следующую свободную из очереди **своей** зоны.
3. Смешанная задача делится: сначала данные/бэкенд, коммит, потом визуал по готовому.
   Не одновременно в одном файле.
4. Своя очередь пуста, чужая нет — не лезь в чужую зону, отметься в `WIP.md` и жди передачи.
5. Пользователь может передать задачу явно — это перебивает зоны.

## Зоны Codex

`launcher/**`, `agent/**`, `dispatch-plugin/**`, `supabase/*.sql`, `gateway/worker.js`,
`server/app/static/supa.js`, inline `<script>` в `tickets.html` / `staff.html` /
`dictionaries.html` / `admin.html`, бэкенд (`server/app/db.py`, `server/app/main.py`,
`server/import_inbox.py`, `publish.py`), `version.json` и release assets.

## Зоны Claude

`server/app/templates/*.html` (кроме перечисленных выше inline-скриптов),
`server/app/static/style.css`, визуальный полиш и тексты, пустые состояния, адаптив,
внешний вид карты, UI-макеты новых страниц без API, QA сайта (`server/qa_check.py`).

## Общие файлы

`AGENTS.md`, `WIP.md`, `HANDOFF.md`, `TECH_ROADMAP.md`, `ROADMAP_TEAM.md`,
`PLAYER_ROADMAP.md`, `PLAYER_UPDATES.md` — правим только свои строки и сразу коммитим.

## Классы, которые нельзя удалять и переименовывать

`sb-edit`, `sb-badge`, `sb-rank`, `sb-dept`, `sb-rankdept`, `sb-role`, `sb-role-badge`,
`nav-drop`, `nav-menu`, `nav-toggle`, `admin-only`, `auth-slot`, `tk-*`, `dic-*`,
`mod-*`, `empty`, `empty-sub`. Стилизовать можно.
