-- ============================================================
--  Чат-поддержка (как у Vinewood): игрок без входа пишет в поддержку,
--  прикладывает лог/скрин, видит ответы оператора. Читает ТОЛЬКО свои
--  тикеты (по заголовку x-client-id). Админ видит и отвечает на всё.
-- ============================================================

alter table public.tickets         add column if not exists client_id text;
alter table public.tickets         add column if not exists user_id uuid references auth.users(id) on delete set null;
alter table public.tickets         add column if not exists callsign text;
alter table public.ticket_comments add column if not exists client_id text;
alter table public.ticket_comments add column if not exists user_id uuid references auth.users(id) on delete set null;
alter table public.ticket_comments add column if not exists from_admin boolean default false;
alter table public.ticket_comments add column if not exists attachment_url text;

-- аноним может создавать тикет и сообщения
drop policy if exists tickets_insert on public.tickets;
create policy tickets_insert on public.tickets
  for insert to anon, authenticated with check (true);

drop policy if exists tcom_insert on public.ticket_comments;
create policy tcom_insert on public.ticket_comments
  for insert to anon, authenticated with check (true);

-- читать: админ — всё; игрок — только свои (по заголовку x-client-id)
drop policy if exists tickets_read on public.tickets;
create policy tickets_read on public.tickets for select using (
  public.is_admin()
  or user_id = auth.uid()
  or client_id = ((current_setting('request.headers', true))::json ->> 'x-client-id')
);

drop policy if exists tcom_read on public.ticket_comments;
create policy tcom_read on public.ticket_comments for select using (
  public.is_admin()
  or user_id = auth.uid()
  or client_id = ((current_setting('request.headers', true))::json ->> 'x-client-id')
);

-- админ может менять тикеты (статус/назначение)
drop policy if exists tickets_update on public.tickets;
create policy tickets_update on public.tickets
  for update using (public.is_admin()) with check (public.is_admin());

-- from_admin проставляется сервером по факту прав (игрок не подделает)
create or replace function public.set_comment_admin()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  new.from_admin := public.is_admin();
  return new;
end $$;
drop trigger if exists trg_comment_admin on public.ticket_comments;
create trigger trg_comment_admin before insert on public.ticket_comments
  for each row execute function public.set_comment_admin();

-- хранилище вложений (лог RagePluginHook, скрины)
insert into storage.buckets (id, name, public)
  values ('support', 'support', true) on conflict (id) do nothing;

drop policy if exists support_upload on storage.objects;
create policy support_upload on storage.objects
  for insert to anon, authenticated with check (bucket_id = 'support');

drop policy if exists support_read on storage.objects;
create policy support_read on storage.objects
  for select using (bucket_id = 'support');
