-- ============================================================
--  LAPD Records — единые тикеты: сайт + лаунчер + Discord.
--  Идемпотентно: можно запускать повторно после schema.sql/chat.sql.
-- ============================================================

alter table public.tickets add column if not exists client_id text;
alter table public.tickets add column if not exists callsign text;
alter table public.tickets add column if not exists source text not null default 'site';
alter table public.tickets add column if not exists author_discord_id text;
alter table public.tickets add column if not exists discord_channel_id text;
alter table public.tickets add column if not exists discord_thread_id text;
alter table public.tickets add column if not exists discord_message_id text;
alter table public.tickets add column if not exists last_message_at timestamptz default now();
alter table public.tickets add column if not exists closed_at timestamptz;

alter table public.ticket_comments add column if not exists client_id text;
alter table public.ticket_comments add column if not exists from_admin boolean default false;
alter table public.ticket_comments add column if not exists attachment_url text;
alter table public.ticket_comments add column if not exists source text not null default 'site';
alter table public.ticket_comments add column if not exists discord_message_id text;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'tickets_source_check') then
    alter table public.tickets
      add constraint tickets_source_check check (source in ('site', 'launcher', 'discord'));
  end if;

  if not exists (select 1 from pg_constraint where conname = 'ticket_comments_source_check') then
    alter table public.ticket_comments
      add constraint ticket_comments_source_check check (source in ('site', 'launcher', 'discord'));
  end if;
end $$;

create table if not exists public.ticket_attachments (
  id bigserial primary key,
  ticket_id bigint references public.tickets(id) on delete cascade,
  comment_id bigint references public.ticket_comments(id) on delete set null,
  client_id text,
  source text not null default 'site',
  file_name text,
  mime_type text,
  size_bytes bigint,
  url text not null,
  storage_path text,
  created_at timestamptz default now()
);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'ticket_attachments_source_check') then
    alter table public.ticket_attachments
      add constraint ticket_attachments_source_check check (source in ('site', 'launcher', 'discord'));
  end if;
end $$;

create index if not exists tickets_status_updated_idx on public.tickets (status, updated_at desc);
create index if not exists tickets_source_idx on public.tickets (source, created_at desc);
create index if not exists tickets_discord_channel_idx on public.tickets (discord_channel_id)
  where discord_channel_id is not null;
create index if not exists ticket_comments_ticket_created_idx on public.ticket_comments (ticket_id, created_at);
create index if not exists ticket_comments_discord_message_idx on public.ticket_comments (discord_message_id)
  where discord_message_id is not null;

alter table public.ticket_attachments enable row level security;

drop policy if exists tickets_insert on public.tickets;
create policy tickets_insert on public.tickets
  for insert to anon, authenticated with check (true);

drop policy if exists tcom_insert on public.ticket_comments;
create policy tcom_insert on public.ticket_comments
  for insert to anon, authenticated with check (true);

drop policy if exists tickets_read on public.tickets;
create policy tickets_read on public.tickets for select using (
  public.is_admin()
  or client_id = ((current_setting('request.headers', true))::json ->> 'x-client-id')
);

drop policy if exists tcom_read on public.ticket_comments;
create policy tcom_read on public.ticket_comments for select using (
  public.is_admin()
  or client_id = ((current_setting('request.headers', true))::json ->> 'x-client-id')
);

drop policy if exists tickets_update on public.tickets;
create policy tickets_update on public.tickets
  for update using (public.is_admin()) with check (public.is_admin());

drop policy if exists ticket_attachments_insert on public.ticket_attachments;
create policy ticket_attachments_insert on public.ticket_attachments
  for insert to anon, authenticated with check (true);

drop policy if exists ticket_attachments_read on public.ticket_attachments;
create policy ticket_attachments_read on public.ticket_attachments for select using (
  public.is_admin()
  or client_id = ((current_setting('request.headers', true))::json ->> 'x-client-id')
);

create or replace function public.set_comment_admin()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  new.from_admin := public.is_admin();
  return new;
end $$;
drop trigger if exists trg_comment_admin on public.ticket_comments;
create trigger trg_comment_admin before insert on public.ticket_comments
  for each row execute function public.set_comment_admin();

create or replace function public.touch_ticket_from_comment()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  update public.tickets
     set updated_at = now(),
         last_message_at = now()
   where id = new.ticket_id;
  return new;
end $$;
drop trigger if exists trg_touch_ticket_from_comment on public.ticket_comments;
create trigger trg_touch_ticket_from_comment after insert on public.ticket_comments
  for each row execute function public.touch_ticket_from_comment();

create or replace function public.mark_ticket_closed_at()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if new.status = 'closed' and old.status is distinct from 'closed' then
    new.closed_at := now();
  elsif new.status is distinct from 'closed' then
    new.closed_at := null;
  end if;
  new.updated_at := now();
  return new;
end $$;
drop trigger if exists trg_mark_ticket_closed_at on public.tickets;
create trigger trg_mark_ticket_closed_at before update on public.tickets
  for each row execute function public.mark_ticket_closed_at();
