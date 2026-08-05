-- ============================================================
--  LAPD Records — роли администрации, модерации и хелперов.
--  Запусти в Supabase SQL Editor. Идемпотентно: можно прогонять повторно.
-- ============================================================

alter table public.roles add column if not exists description text;
alter table public.roles add column if not exists role_level int not null default 10;
alter table public.roles add column if not exists can_staff boolean not null default false;
alter table public.roles add column if not exists can_dictionaries boolean not null default false;
alter table public.roles add column if not exists can_moderate boolean not null default false;
alter table public.roles add column if not exists can_audit boolean not null default false;
alter table public.roles add column if not exists can_admins boolean not null default false;

create table if not exists public.departments (
  id serial primary key,
  name text unique not null,
  color text,
  ord int default 0
);
alter table public.departments enable row level security;
drop policy if exists departments_read on public.departments;
create policy departments_read on public.departments for select using (true);

alter table public.admins add column if not exists role text not null default 'admin';
alter table public.admins add column if not exists display_name text;
alter table public.admins add column if not exists status text not null default 'active';
alter table public.admins add column if not exists protected boolean not null default false;
alter table public.admins add column if not exists notes text;
alter table public.admins add column if not exists updated_at timestamptz default now();
alter table public.admins add column if not exists updated_by uuid references auth.users(id) on delete set null;

insert into public.roles
  (name, title, description, role_level, can_manage, can_tickets, can_staff,
   can_dictionaries, can_moderate, can_audit, can_admins)
values
  ('owner', 'Главный админ', 'Полный доступ. Нельзя снять или понизить через панель другим ролям.', 100,
   true, true, true, true, true, true, true),
  ('admin', 'Админ', 'Оперативное управление сайтом, персоналом, справочниками и тикетами.', 80,
   true, true, true, true, true, true, false),
  ('moderator', 'Модератор', 'Модерация заявок, персонала и тикетов без доступа к выдаче админов.', 60,
   false, true, true, false, true, true, false),
  ('helper', 'Хелпер', 'Ответы игрокам в поддержке и помощь по логам без доступа к персоналу.', 40,
   false, true, false, false, false, false, false),
  ('officer', 'Офицер', 'Обычный сотрудник департамента.', 20,
   false, false, false, false, false, false, false),
  ('viewer', 'Наблюдатель', 'Только просмотр публичных страниц.', 10,
   false, false, false, false, false, false, false)
on conflict (name) do update set
  title = excluded.title,
  description = excluded.description,
  role_level = excluded.role_level,
  can_manage = excluded.can_manage,
  can_tickets = excluded.can_tickets,
  can_staff = excluded.can_staff,
  can_dictionaries = excluded.can_dictionaries,
  can_moderate = excluded.can_moderate,
  can_audit = excluded.can_audit,
  can_admins = excluded.can_admins;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'admins_role_fk'
  ) then
    alter table public.admins add constraint admins_role_fk
      foreign key (role) references public.roles(name) on delete restrict;
  end if;
end $$;

create or replace function public.current_admin_role()
returns text
language sql stable
security definer set search_path = public
as $$
  select coalesce((
    select a.role from public.admins a
    where a.status = 'active'
      and (a.user_id = auth.uid()
        or (a.email is not null and lower(a.email) = lower(coalesce(auth.jwt() ->> 'email', ''))))
    limit 1
  ), 'viewer');
$$;

create or replace function public.has_admin_perm(_perm text)
returns boolean
language plpgsql stable
security definer set search_path = public
as $$
declare r public.roles%rowtype;
begin
  select * into r from public.roles where name = public.current_admin_role();
  if not found then
    return false;
  end if;
  case _perm
    when 'owner' then return r.name = 'owner';
    when 'admin' then return r.name in ('owner', 'admin');
    when 'tickets' then return r.can_tickets;
    when 'staff' then return r.can_staff;
    when 'dictionaries' then return r.can_dictionaries;
    when 'moderate' then return r.can_moderate;
    when 'audit' then return r.can_audit;
    when 'admins' then return r.can_admins;
    when 'access_admin' then return r.can_tickets or r.can_staff or r.can_dictionaries or r.can_audit or r.can_admins;
    else return false;
  end case;
end;
$$;

create or replace function public.is_admin()
returns boolean
language sql stable
security definer set search_path = public
as $$
  select public.has_admin_perm('admin');
$$;

create or replace function public.can_manage_staff()
returns boolean
language sql stable
security definer set search_path = public
as $$ select public.has_admin_perm('staff'); $$;

create or replace function public.can_manage_dictionaries()
returns boolean
language sql stable
security definer set search_path = public
as $$ select public.has_admin_perm('dictionaries'); $$;

create or replace function public.can_handle_tickets()
returns boolean
language sql stable
security definer set search_path = public
as $$ select public.has_admin_perm('tickets'); $$;

create or replace function public.set_comment_admin()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  new.from_admin := public.can_handle_tickets();
  return new;
end;
$$;

create or replace function public.my_permissions()
returns jsonb
language sql stable
security definer set search_path = public
as $$
  select jsonb_build_object(
    'role', r.name,
    'title', r.title,
    'level', r.role_level,
    'is_owner', r.name = 'owner',
    'is_admin', r.name in ('owner', 'admin'),
    'can_access_admin', public.has_admin_perm('access_admin'),
    'can_tickets', r.can_tickets,
    'can_staff', r.can_staff,
    'can_dictionaries', r.can_dictionaries,
    'can_moderate', r.can_moderate,
    'can_audit', r.can_audit,
    'can_admins', r.can_admins
  )
  from public.roles r
  where r.name = public.current_admin_role();
$$;

create or replace function public.list_admin_users()
returns table (
  user_id uuid,
  email text,
  display_name text,
  role text,
  role_title text,
  status text,
  protected boolean,
  notes text,
  added_at timestamptz,
  updated_at timestamptz
)
language sql stable
security definer set search_path = public
as $$
  select a.user_id, a.email, a.display_name, a.role, r.title, a.status,
         a.protected, a.notes, a.added_at, a.updated_at
  from public.admins a
  left join public.roles r on r.name = a.role
  where public.has_admin_perm('admins')
  order by coalesce(r.role_level, 0) desc, a.added_at asc;
$$;

create or replace function public.set_admin_role(
  _email text,
  _role text,
  _status text default 'active',
  _display_name text default null,
  _notes text default null
)
returns void
language plpgsql
security definer set search_path = public
as $$
declare
  actor_role text := public.current_admin_role();
  actor_level int := 0;
  target_level int := 0;
  target_user uuid;
  target_old public.admins%rowtype;
begin
  if not public.has_admin_perm('admins') then
    raise exception 'Недостаточно прав для управления администрацией';
  end if;

  select role_level into actor_level from public.roles where name = actor_role;
  select role_level into target_level from public.roles where name = _role;
  if target_level is null then
    raise exception 'Неизвестная роль: %', _role;
  end if;

  if actor_role <> 'owner' and _role in ('owner', 'admin') then
    raise exception 'Только главный админ может выдавать роль главного админа или админа';
  end if;

  select id into target_user from auth.users where lower(email) = lower(_email) limit 1;
  if target_user is null then
    raise exception 'Пользователь с таким email ещё не входил через Discord/Supabase';
  end if;

  select * into target_old from public.admins where user_id = target_user;
  if found and target_old.protected and actor_role <> 'owner' then
    raise exception 'Защищённую учётку может менять только главный админ';
  end if;
  if found and target_old.role = 'owner' and actor_role <> 'owner' then
    raise exception 'Главного админа может менять только главный админ';
  end if;

  insert into public.admins (user_id, email, display_name, role, status, notes, protected, updated_at, updated_by)
  values (target_user, lower(_email), nullif(_display_name, ''), _role,
          coalesce(nullif(_status, ''), 'active'), nullif(_notes, ''),
          case when _role = 'owner' then true else false end, now(), auth.uid())
  on conflict (user_id) do update set
    email = excluded.email,
    display_name = excluded.display_name,
    role = excluded.role,
    status = excluded.status,
    notes = excluded.notes,
    protected = case
      when public.admins.protected and actor_role <> 'owner' then public.admins.protected
      when excluded.role = 'owner' then true
      else public.admins.protected
    end,
    updated_at = now(),
    updated_by = auth.uid();

  perform public.log_action(
    'admin.role.set',
    'admin',
    lower(_email),
    jsonb_build_object('role', _role, 'status', _status, 'display_name', _display_name)
  );
end;
$$;

create or replace function public.protect_admin(_email text, _protected boolean default true)
returns void
language plpgsql
security definer set search_path = public
as $$
declare target_user uuid;
begin
  if public.current_admin_role() <> 'owner' then
    raise exception 'Только главный админ может включать защиту';
  end if;
  select id into target_user from auth.users where lower(email) = lower(_email) limit 1;
  if target_user is null then
    raise exception 'Пользователь с таким email ещё не входил';
  end if;
  update public.admins
  set protected = _protected, updated_at = now(), updated_by = auth.uid()
  where user_id = target_user;
  perform public.log_action('admin.protect', 'admin', lower(_email), jsonb_build_object('protected', _protected));
end;
$$;

drop policy if exists ranks_write on public.ranks;
create policy ranks_write on public.ranks for all
  using (public.can_manage_dictionaries()) with check (public.can_manage_dictionaries());

drop policy if exists departments_write on public.departments;
create policy departments_write on public.departments for all
  using (public.can_manage_dictionaries()) with check (public.can_manage_dictionaries());

drop policy if exists roles_write on public.roles;
create policy roles_write on public.roles for all
  using (public.has_admin_perm('admins')) with check (public.has_admin_perm('admins'));

drop policy if exists officer_profiles_write on public.officer_profiles;
create policy officer_profiles_write on public.officer_profiles for all
  using (public.can_manage_staff()) with check (public.can_manage_staff());

drop policy if exists tickets_update on public.tickets;
create policy tickets_update on public.tickets
  for update using (public.can_handle_tickets()) with check (public.can_handle_tickets());

drop policy if exists ticket_comments_admin_read on public.ticket_comments;
create policy ticket_comments_admin_read on public.ticket_comments
  for select using (public.can_handle_tickets());

drop policy if exists audit_admin on public.audit_log;
create policy audit_admin on public.audit_log for select using (public.has_admin_perm('audit'));

drop policy if exists admins_read on public.admins;
create policy admins_read on public.admins for select using (public.has_admin_perm('admins'));

-- Главный админ: выполни один раз после своего входа через Discord/Supabase.
-- Замени email на тот, который виден в Supabase Auth для твоего аккаунта.
--
-- insert into public.admins (user_id, email, display_name, role, status, protected)
-- select id, lower(email), 'osminoowka', 'owner', 'active', true
-- from auth.users
-- where lower(email) = lower('ТВОЙ_EMAIL_ИЗ_SUPABASE_AUTH')
-- on conflict (user_id) do update set
--   role = 'owner',
--   status = 'active',
--   protected = true,
--   display_name = excluded.display_name,
--   updated_at = now();
