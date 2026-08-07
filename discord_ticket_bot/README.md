# LAPD Records Discord Ticket Bot

Бот связывает Discord, сайт `/support`, лаунчер и админскую страницу `/tickets` в одну очередь.

## Что умеет

- Публикует кнопку `Создать тикет` в канале поддержки.
- Создаёт приватный Discord-канал под каждый тикет.
- Записывает сообщения из Discord в Supabase `ticket_comments`.
- Подхватывает тикеты с сайта/лаунчера без Discord-канала и создаёт канал сам.
- Пересылает ответы операторов с сайта `/tickets` обратно в Discord.
- Команда `!close` закрывает тикет в Supabase и блокирует канал от новых сообщений игрока.

## Первый запуск

1. В Supabase SQL Editor выполнить `supabase/unified_tickets.sql`.
2. Создать Discord bot application и включить `Message Content Intent`.
3. Пригласить бота на сервер с правами:
   - Manage Channels
   - Send Messages
   - Read Message History
   - View Channels
4. Создать `.env` рядом с `bot.py` по примеру `.env.example`.
5. Установить зависимости:

```powershell
python -m pip install -r discord_ticket_bot/requirements.txt
```

6. Запустить:

```powershell
python discord_ticket_bot/bot.py
```

7. В канале поддержки написать:

```text
!ticket-panel
```

Бот отправит красивую карточку с кнопкой создания тикета.

## Важно по секретам

`SUPABASE_SERVICE_ROLE_KEY` и `DISCORD_BOT_TOKEN` нельзя вставлять в сайт, лаунчер и публичный репозиторий. Они должны лежать только в `.env` на машине/сервере, где запущен бот.
