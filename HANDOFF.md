# LAPD Records handoff

Последнее обновление: 2026-08-05, Codex.

## Текущее состояние

Сайт собран и запушен в `main`. Последний проверенный коммит перед созданием этих документов: `56ffa16` (`Polish visible records text`).

Рабочая система:

- Главная страница, записи, суд, смены, карта, персонал, регистрация.
- Статический экспорт в `docs/`.
- Supabase-страницы: тикеты, справочники, персонал.
- Лаунчер и агент не трогались в последнем визуальном QA-срезе.

## Последние важные правки

- Исправлены видимые английские хвосты в протоколах и судах.
- Сырые ISO-даты заменены на нормальный формат.
- Добавлена мягкая очистка mojibake при выводе.
- Убрана публичная dev-кнопка `+ тест-смена`.
- Пересобран `docs/`.
- Добавлен `CLAUDE_QA_NOTES.md` с QA-чеклистом для Claude.

## Что нельзя забыть следующему агенту

- `docs/` не править руками.
- Любой визуальный фикс в шаблонах/стилях после этого требует `python server/export_static.py`.
- Не трогать Supabase JS без отдельной задачи.
- Карта содержит inline JS в `map.html`; если меняешь классы/атрибуты секторов, проверяй hover/click.
- PowerShell может показывать кириллицу как mojibake, но браузер и файлы могут быть нормальными. Для проверки кодировки лучше смотреть HTML через `rg` или `unicode_escape`, а не глазами в старой консоли.

## Быстрая проверка

```powershell
python -m py_compile server/app/db.py server/app/main.py server/app/discord_post.py server/export_static.py
python server/export_static.py
python -c "from app.main import app; c=app.test_client(); paths=['/','/cases','/case/19','/court/20','/shifts','/map','/register','/staff','/tickets','/dictionaries']; [print(p, c.get(p).status_code) for p in paths]"
rg -n "Wobbler|arrested|test-смена|CITATIONS|RECORDS|COURT|T[0-9]{2}:[0-9]{2}:[0-9]{2}|Рљ|Р‘СЂ|Р°РІРµ|Courtroom|Court-Appointed|CJA Panel" docs -g "*.html"
```

## Следующий хороший срез

Сделать страницу “Поддержка” как красивый UI-макет без AI API:

- описание проблемы;
- загрузка `.log` / `.txt`;
- блок результата диагностики;
- кнопка создания тикета;
- список известных ошибок и готовых советов.

Логику AI/API не подключать в этом срезе.

