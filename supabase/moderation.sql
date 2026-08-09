-- ============================================================
--  LAPD Records — модерация офицеров (одобрение через сайт).
--  Позволяет владельцу/модератору одобрять офицеров кнопкой в /admin
--  и/или включить авто-одобрение. Импорт (GitHub Actions) читает эти
--  таблицы и публикует данные одобренных, а неодобренных держит на модерации.
--
--  Запусти это в Supabase → SQL Editor → New query → Run. Идемпотентно.
--  Требует ранее применённого supabase/admin_roles.sql (функция can_manage_staff()).
-- ============================================================

-- ---------- одобренные офицеры (реестр) ----------
create table if not exists public.roster (
  callsign  text primary key,
  name      text,
  discord   text,
  is_admin  boolean not null default false,
  added_by  text,
  added_at  timestamptz default now()
);

-- ---------- на модерации (ждут одобрения) ----------
create table if not exists public.pending_officers (
  callsign    text primary key,
  name        text,
  discord     text,
  submissions int not null default 1,
  first_seen  timestamptz default now(),
  last_seen   timestamptz default now()
);

-- ---------- настройка авто-одобрения (одна строка) ----------
create table if not exists public.moderation (
  id           int primary key default 1,
  auto_approve boolean not null default false,
  updated_by   text,
  updated_at   timestamptz default now(),
  constraint moderation_single_row check (id = 1)
);
insert into public.moderation (id, auto_approve) values (1, false)
  on conflict (id) do nothing;

-- ============================================================
--  RLS: читать могут все (сайт статичный + импорт с publishable-ключом);
--  писать/одобрять — только тот, кто управляет персоналом (модератор+).
-- ============================================================
alter table public.roster            enable row level security;
alter table public.pending_officers  enable row level security;
alter table public.moderation        enable row level security;

drop policy if exists roster_read on public.roster;
create policy roster_read on public.roster for select using (true);
drop policy if exists pending_read on public.pending_officers;
create policy pending_read on public.pending_officers for select using (true);
drop policy if exists moderation_read on public.moderation;
create policy moderation_read on public.moderation for select using (true);

drop policy if exists roster_write on public.roster;
create policy roster_write on public.roster for all
  using (public.can_manage_staff()) with check (public.can_manage_staff());
drop policy if exists pending_write on public.pending_officers;
create policy pending_write on public.pending_officers for all
  using (public.can_manage_staff()) with check (public.can_manage_staff());
drop policy if exists moderation_write on public.moderation;
create policy moderation_write on public.moderation for all
  using (public.can_manage_staff()) with check (public.can_manage_staff());

-- ============================================================
--  RPC
-- ============================================================

-- Импорт (anon) сообщает о новом НЕодобренном офицере → в pending.
create or replace function public.report_pending(_callsign text, _name text default null, _discord text default null)
returns void language plpgsql security definer set search_path = public as $$
begin
  if _callsign is null or length(trim(_callsign)) = 0 then
    return;
  end if;
  -- уже одобрен — не засоряем модерацию
  if exists (select 1 from public.roster r where lower(r.callsign) = lower(_callsign)) then
    return;
  end if;
  insert into public.pending_officers as p (callsign, name, discord, submissions, first_seen, last_seen)
  values (_callsign, _name, _discord, 1, now(), now())
  on conflict (callsign) do update
    set submissions = p.submissions + 1,
        last_seen   = now(),
        name        = coalesce(excluded.name, p.name),
        discord     = coalesce(excluded.discord, p.discord);
end; $$;

-- Одобрить офицера (только staff): в roster + убрать из pending. Работает и для
-- ручного ввода позывного, которого нет в pending.
create or replace function public.approve_officer(_callsign text, _name text default null)
returns void language plpgsql security definer set search_path = public as $$
declare _pname text; _pdiscord text;
begin
  if not public.can_manage_staff() then
    raise exception 'нет прав на модерацию';
  end if;
  select name, discord into _pname, _pdiscord
    from public.pending_officers where lower(callsign) = lower(_callsign) limit 1;
  insert into public.roster (callsign, name, discord, added_by, added_at)
  values (_callsign, coalesce(_name, _pname), _pdiscord, coalesce(auth.jwt() ->> 'email','admin'), now())
  on conflict (callsign) do update
    set name = coalesce(excluded.name, public.roster.name);
  delete from public.pending_officers where lower(callsign) = lower(_callsign);
end; $$;

-- Отклонить (убрать из pending без одобрения).
create or replace function public.reject_officer(_callsign text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.can_manage_staff() then
    raise exception 'нет прав на модерацию';
  end if;
  delete from public.pending_officers where lower(callsign) = lower(_callsign);
end; $$;

-- Переключить авто-одобрение (только staff).
create or replace function public.set_auto_approve(_on boolean)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.can_manage_staff() then
    raise exception 'нет прав на модерацию';
  end if;
  update public.moderation
     set auto_approve = _on, updated_by = coalesce(auth.jwt() ->> 'email','admin'), updated_at = now()
   where id = 1;
end; $$;

grant execute on function public.report_pending(text, text, text) to anon, authenticated;
grant execute on function public.approve_officer(text, text)       to authenticated;
grant execute on function public.reject_officer(text)              to authenticated;
grant execute on function public.set_auto_approve(boolean)         to authenticated;

-- ---------- сид одобренных из текущего roster.json ----------
insert into public.roster (callsign, name, is_admin) values
  ('1-ADAM-13',   'Tim Bredford',   true),
  ('7-WILLIAM-1', 'Denis Sherman',  true),
  ('3-LINCOLN-17','Matthew Redview', false)
on conflict (callsign) do nothing;
