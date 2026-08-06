# LAPD Records — аудит 2026-08-07

Цель: проверить, почему игрок всё ещё видел ZIP вместо установщика, пройти сайт на мелкие ошибки
и оставить понятный след для Claude/Codex.

## Итог по установщику

- Live `/launcher/` уже отдаёт `LAPD-Records-Launcher-Setup.exe`.
- Live `/register/` тоже отдаёт `LAPD-Records-Launcher-Setup.exe`.
- Старый `LAPD-Records-Launcher.zip` на публичных страницах не найден.
- Прямая ссылка установщика живая:
  `https://github.com/osminoog09-star/dispatch-one-records/releases/latest/download/LAPD-Records-Launcher-Setup.exe`
- ZIP остаётся только техническим пакетом для `version.json.launcher_url`, установщика и автообновления лаунчера.

Если игрок видит ZIP в окне скачивания, вероятнее всего открыта старая вкладка или кэш браузера.
Нужно обновить страницу `/launcher/` через Ctrl+F5 или открыть ссылку заново.

## Проверки

- Git: `main` синхронизирован с `origin/main`.
- Release assets:
  - `LAPD-Records-Launcher-Setup.exe` — HTTP 200.
  - `LAPD-Records-Launcher.zip` — HTTP 200.
  - `pdcomp_sync.exe` — HTTP 200.
- Flask smoke:
  - `/`, `/launcher`, `/register`, `/cases`, `/case/19`, `/citations`, `/citation/7`,
    `/court`, `/court/20`, `/files`, `/file/Eddie%20Thomas`, `/officer/7-WILLIAM-1`,
    `/shifts`, `/shift/10`, `/map`, `/tickets`, `/callouts`, `/callout/7`,
    `/vehicles`, `/warnings`, `/admin`, `/staff`, `/dictionaries` — все 200.
- Static docs crawler:
  - 115 страниц.
  - 3566 внутренних ссылок.
  - 0 битых внутренних ссылок.
  - 0 публичных вхождений старого ZIP/старого onefile EXE/`NaN`/`undefined`.
- Python compile:
  - `launcher/launcher.py`
  - `launcher/setup_installer.py`
  - `agent/pdcomp_sync.py`
  - `server/app/main.py`
  - `server/app/db.py`
  - `server/app/discord_post.py`
  - `server/export_static.py`
  - `server/import_inbox.py`
  - `publish.py`
- Live visual smoke через Playwright:
  - `/`, `/launcher/`, `/register/`, `/map/`, `/officer/7-WILLIAM-1/`, `/tickets/`.
  - CSS грузится.
  - `/launcher/` и `/register/` содержат Setup.exe и не содержат ZIP.

## Найдено и исправлено

- GitHub Actions `build-site` имел старый queued run и несколько cancelled/failed runs.
- Токен релизов не имеет `actions:write`, поэтому старый queued run нельзя отменить через API из локального скрипта.
- Workflow обновлён:
  - добавлены триггеры на `.github/workflows/build-site.yml`, `version.json`, `server/export_static.py`;
  - `concurrency.cancel-in-progress` включён, чтобы новые сборки отменяли старые зависшие;
  - перед `git push` в автосборке добавлен `git pull --rebase origin main`, чтобы снизить шанс push-конфликта.

## Что не трогать

- Не менять `version.json.launcher_url` на Setup.exe. Это должен быть ZIP для автообновления.
- Публичные кнопки сайта должны вести на `version.json.installer_url` / `LAPD-Records-Launcher-Setup.exe`.
- Не редактировать `docs/` руками, кроме результата `python server/export_static.py`.
- Не трогать Supabase JS-логику без отдельной задачи.

## Что дальше по плану

1. Поддержка: добавить диагностику логов без AI API, чтобы игрок вставил лог и получил понятный ответ.
2. Discord/Actions: после push проверить новый workflow run; если опять падает, разбирать конкретный job log.
3. Админка: довести роли и полномочия до полного рабочего сценария для owner/admin/mod/helper.
4. Карта: добавить переходы из дела/вызова на район и позже координатную привязку.
5. Статистика: расширить отчёты за 24 часа, 7 дней, 30 дней и смены.
6. Лаунчер: отдельный экран состояния установки — версия, путь, агент, автозапуск, кнопка переустановки/удаления.
