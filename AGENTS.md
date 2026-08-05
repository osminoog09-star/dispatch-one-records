# LAPD Records agent protocol

Этот файл обязателен для Codex, Claude и любого следующего агента. Цель: ускорить разработку без поломки рабочей системы.

## Главные правила

1. Работать маленькими проверяемыми срезами: одна задача = один понятный результат.
2. Перед стартом читать `HANDOFF.md`, `WIP.md`, `TECH_ROADMAP.md` и `CLAUDE_QA_NOTES.md`.
3. Перед изменениями проверять `git status --short --branch`.
4. Если задача уже помечена в `WIP.md` как `IN PROGRESS` другим агентом, не брать её.
5. Когда берёшь задачу, записать её в `WIP.md` как `IN PROGRESS` с автором и датой.
6. После завершения убрать задачу из активного блока `WIP.md` и обновить `HANDOFF.md`.
7. `docs/` руками не редактировать: это GitHub Pages экспорт. Править источники в `server/app`, затем запускать `python server/export_static.py`.
8. Не делать большие рефакторы “заодно”. Если видишь проблему вне задачи, занеси её в `TECH_ROADMAP.md`.

## Строго нельзя трогать без отдельной задачи

- `server/app/static/supa.js`
- inline JS в `server/app/templates/tickets.html`
- inline JS в `server/app/templates/staff.html`
- inline JS в `server/app/templates/dictionaries.html`
- `server/app/db.py`, `server/app/main.py`, `publish.py`, `server/export_static.py`, если задача только про внешний вид
- `launcher/launcher.py`
- `agent/pdcomp_sync.py`
- `supabase/*.sql`
- `gateway/worker.js`

Исключение: можно делать точечное безопасное форматирование вывода, если пользователь явно просит исправить видимые косяки и есть проверка после правки.

## JS-зависимые классы

Эти классы можно стилизовать, но нельзя удалять или переименовывать:

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

## Рабочий цикл

1. Прочитать `HANDOFF.md`, `WIP.md`, `TECH_ROADMAP.md`, `CLAUDE_QA_NOTES.md`.
2. Проверить `git status --short --branch`.
3. Выбрать один маленький срез из `TECH_ROADMAP.md`.
4. Записать его в `WIP.md` как `IN PROGRESS`.
5. Сделать изменения.
6. Запустить проверки из раздела ниже.
7. Если менялись шаблоны/стили/данные сайта, запустить `python server/export_static.py`.
8. Проверить `git diff --stat` и убедиться, что нет случайных файлов.
9. Обновить `HANDOFF.md` и `WIP.md`.
10. Commit + push.

## Минимальные проверки

Для любых Python-правок:

```powershell
python -m py_compile server/app/db.py server/app/main.py server/app/discord_post.py server/export_static.py
```

Для правок сайта:

```powershell
python server/export_static.py
python -c "from app.main import app; c=app.test_client(); paths=['/','/cases','/case/19','/court/20','/shifts','/map','/register','/staff','/tickets','/dictionaries']; [print(p, c.get(p).status_code) for p in paths]"
rg -n "Wobbler|arrested|test-смена|CITATIONS|RECORDS|COURT|T[0-9]{2}:[0-9]{2}:[0-9]{2}|Рљ|Р‘СЂ|Р°РІРµ|Courtroom|Court-Appointed|CJA Panel" docs -g "*.html"
```

Последний `rg` должен быть пустым или содержать только явно допустимые технические meta/comment строки, которые не видны игроку.

## Как дробить задачи

Хороший размер задачи:

- “почистить страницу смен и проверить 200”
- “улучшить пустые состояния во всех таблицах”
- “доработать карту без изменения JS-контракта”
- “русифицировать протокол суда”
- “добавить поддержку загрузки логов только в UI-макете, без API”

Плохой размер задачи:

- “переделать весь сайт и логику”
- “починить Supabase, карту, лаунчер и суды сразу”
- “сделать красиво где-нибудь”

## Git

- Рабочая ветка по умолчанию: `main`, если пользователь не попросил иначе.
- Перед push убедиться, что `git status --short` содержит только ожидаемые файлы.
- Сообщение коммита должно быть коротким и по делу, например `Polish visible records text`.

