-- ============================================================
--  LAPD Records — схема Supabase (Postgres)
--  Звания, роли, профили офицеров, тикеты, логирование.
--  Запусти это в Supabase → SQL Editor → New query → Run.
--  Идемпотентно: можно прогонять повторно.
-- ============================================================

-- ---------- helper: кто админ (по auth.uid или email) ----------
create table if not exists public.admins (
  user_id uuid references auth.users(id) on delete cascade,
  email   text,
  added_at timestamptz default now(),
  primary key (user_id)
);

-- функция: текущий пользователь — админ?
create or replace function public.is_admin()
returns boolean
language sql stable
security definer set search_path = public
as $$
  select exists (
    select 1 from public.admins a
    where a.user_id = auth.uid()
       or (a.email is not null and a.email = auth.jwt() ->> 'email')
  );
$$;

-- ---------- звания ----------
create table if not exists public.ranks (
  id serial primary key,
  name text not null unique,        -- «Офицер», «Сержант», «Лейтенант»…
  abbr text,                        -- «Off.», «Sgt.»
  level int not null default 0,     -- для сортировки/иерархии
  color text,                       -- #hex для бейджа
  created_at timestamptz default now()
);

-- ---------- роли (права на сайте) ----------
create table if not exists public.roles (
  id serial primary key,
  name text not null unique,        -- «admin», «supervisor», «officer», «viewer»
  title text,                       -- человекочитаемо: «Администратор»
  can_manage boolean default false, -- может менять роли/звания
  can_tickets boolean default false -- может вести тикеты
);

-- ---------- профиль офицера (роль/звание на каждого) ----------
create table if not exists public.officer_profiles (
  callsign text primary key,        -- связь с офицером сайта (позывной)
  display_name text,
  discord text,
  badge_no text,
  rank_id int references public.ranks(id) on delete set null,
  role text references public.roles(name) on delete set null default 'officer',
  notes text,
  updated_at timestamptz default now(),
  updated_by text
);

-- ---------- тикеты ----------
create table if not exists public.tickets (
  id bigserial primary key,
  title text not null,
  body text,
  status text not null default 'open',    -- open / in_progress / closed
  priority text not null default 'normal', -- low / normal / high / urgent
  category text,                           -- жалоба / рапорт / запрос…
  subject_callsign text,                   -- к какому офицеру/делу
  created_by text,                         -- позывной/имя автора
  assigned_to text,                        -- кому назначен
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.ticket_comments (
  id bigserial primary key,
  ticket_id bigint references public.tickets(id) on delete cascade,
  author text,
  body text not null,
  created_at timestamptz default now()
);

-- ---------- лог действий ----------
create table if not exists public.audit_log (
  id bigserial primary key,
  actor text,                       -- кто (email/позывной)
  action text not null,             -- 'rank.set', 'ticket.create', 'login'…
  entity text,                      -- 'officer' / 'ticket'…
  entity_id text,
  details jsonb,
  created_at timestamptz default now()
);

-- ============================================================
--  ROW LEVEL SECURITY
--  Читать справочники/профили/тикеты — можно всем (сайт статичный,
--  показывает данные анониму). Писать — только админам/уполномоченным.
-- ============================================================
alter table public.ranks             enable row level security;
alter table public.roles             enable row level security;
alter table public.officer_profiles  enable row level security;
alter table public.tickets           enable row level security;
alter table public.ticket_comments   enable row level security;
alter table public.audit_log         enable row level security;
alter table public.admins            enable row level security;

-- читать (anon + authenticated)
do $$
declare t text;
begin
  foreach t in array array['ranks','roles','officer_profiles','tickets','ticket_comments'] loop
    execute format('drop policy if exists %I on public.%I', t||'_read', t);
    execute format('create policy %I on public.%I for select using (true)', t||'_read', t);
  end loop;
end $$;

-- писать справочники/профили — только админ
do $$
declare t text;
begin
  foreach t in array array['ranks','roles','officer_profiles'] loop
    execute format('drop policy if exists %I on public.%I', t||'_write', t);
    execute format('create policy %I on public.%I for all using (public.is_admin()) with check (public.is_admin())', t||'_write', t);
  end loop;
end $$;

-- тикеты: создать может любой вошедший; менять — админ или автор
drop policy if exists tickets_insert on public.tickets;
create policy tickets_insert on public.tickets for insert
  to authenticated with check (true);
drop policy if exists tickets_update on public.tickets;
create policy tickets_update on public.tickets for all
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists tcom_insert on public.ticket_comments;
create policy tcom_insert on public.ticket_comments for insert
  to authenticated with check (true);

-- лог: читать/писать — только админ (писать удобнее через RPC ниже)
drop policy if exists audit_admin on public.audit_log;
create policy audit_admin on public.audit_log for select using (public.is_admin());

-- admins: видеть только админам
drop policy if exists admins_read on public.admins;
create policy admins_read on public.admins for select using (public.is_admin());

-- ---------- запись в лог из клиента (безопасно, через функцию) ----------
create or replace function public.log_action(_action text, _entity text, _entity_id text, _details jsonb default '{}')
returns void language sql security definer set search_path = public as $$
  insert into public.audit_log (actor, action, entity, entity_id, details)
  values (coalesce(auth.jwt() ->> 'email', 'anon'), _action, _entity, _entity_id, _details);
$$;

-- ---------- стартовые данные ----------
insert into public.roles (name, title, can_manage, can_tickets) values
  ('admin','Администратор', true,  true),
  ('supervisor','Супервайзер', false, true),
  ('officer','Офицер', false, false),
  ('viewer','Наблюдатель', false, false)
on conflict (name) do nothing;

insert into public.ranks (name, abbr, level, color) values
  ('Кадет','Cdt.',0,'#8b949e'),
  ('Офицер','Off.',10,'#2f81f7'),
  ('Старший офицер','Sr.Off.',20,'#4c8dff'),
  ('Сержант','Sgt.',30,'#2ea043'),
  ('Лейтенант','Lt.',40,'#e3b341'),
  ('Капитан','Cpt.',50,'#f0883e'),
  ('Шеф полиции','Chief',60,'#f85149')
on conflict (name) do nothing;

-- ЧТОБЫ СДЕЛАТЬ СЕБЯ АДМИНОМ:
-- 1) один раз войди на сайт своим способом (email/Discord),
-- 2) выполни (подставь свой email):
--    insert into public.admins (user_id, email)
--    select id, email from auth.users where email = 'osminoog09@gmail.com'
--    on conflict do nothing;
