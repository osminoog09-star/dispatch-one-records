# Единые тикеты: Discord + лаунчер + сайт

Цель: игрок может создать обращение в трёх местах, а команда поддержки видит одну общую очередь.

## Что уже готово

- Лаунчер создаёт тикеты в Supabase и помечает источник `launcher`.
- Сайт `/support` создаёт тикеты в Supabase и помечает источник `site`.
- Админская страница `/tickets` показывает общую очередь и источник обращения.
- SQL-миграция `supabase/unified_tickets.sql` добавляет поля для Discord-канала/треда и защиты от дублей.

## Как должна работать Discord-часть

1. В Discord игрок жмёт кнопку `Создать тикет` в канале поддержки.
2. Бот создаёт приватный канал или тред: `ticket-0007-7-william-1`.
3. Бот создаёт запись в Supabase `tickets`:
   - `source = 'discord'`
   - `author_discord_id = <discord user id>`
   - `discord_channel_id = <channel id>`
   - `created_by = <discord display name>`
   - `callsign = <если игрок ввёл позывной>`
4. Все сообщения в этом Discord-канале бот пишет в `ticket_comments`:
   - `source = 'discord'`
   - `discord_message_id = <message id>`
   - `ticket_id = <id тикета>`
5. Ответы из сайта `/tickets` бот отправляет обратно в Discord, если у комментария ещё нет `discord_message_id`.
6. Если тикет закрыт на сайте или в Discord, бот ставит `tickets.status = 'closed'`.

## Что нужно в Discord

- Категория: `LAPD Support`.
- Канал входа: `#поддержка`.
- Приватные каналы тикетов: видят игрок, helper/moderator/admin/owner.
- Роли:
  - `Owner` — полный доступ.
  - `Admin` — управление тикетами и ролями поддержки.
  - `Moderator` — обработка тикетов и модерация записей.
  - `Helper` — ответы игрокам и просмотр логов.

## Переменные для будущего бота

Не коммитить реальные значения.

```text
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
DISCORD_TICKET_CATEGORY_ID=
DISCORD_SUPPORT_PANEL_CHANNEL_ID=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

## Защита от дублей

- Discord → Supabase: перед вставкой проверять `ticket_comments.discord_message_id`.
- Supabase → Discord: отправлять только комментарии без `discord_message_id`, потом сразу патчить `discord_message_id`.
- Тикеты лаунчера/сайта без `discord_channel_id` бот один раз подхватывает и создаёт Discord-канал, затем пишет `discord_channel_id`.

## Важное

- Бот должен работать только на сервере/VPS/GitHub Actions worker с секретами. В браузер и лаунчер `SUPABASE_SERVICE_ROLE_KEY` не вставлять.
- Для игрока публичная точка на сайте: `/support`.
- Для команды поддержки: `/tickets`.
