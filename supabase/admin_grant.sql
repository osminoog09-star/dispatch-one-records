-- ============================================================
--  LAPD Records — выдача админки по Discord + публичные бейджи ролей.
--  Требует admin_roles.sql (роли/права) и moderation.sql.
--  Запусти в Supabase SQL Editor. Идемпотентно.
-- ============================================================

-- Список всех, кто заходил на сайт через Discord (для выпадашки в /admin).
-- Показывает Discord-имя, текущую роль и email. Доступно только тем, кто может
-- управлять доступами.
create or replace function public.list_site_users()
returns table (user_id uuid, email text, discord text, role text, role_title text, created_at timestamptz)
language sql stable security definer set search_path = public as $$
  select u.id, u.email,
         coalesce(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name',
                  u.raw_user_meta_data->>'user_name', u.raw_user_meta_data->>'preferred_username', u.email) as discord,
         coalesce(a.role, '—'), r.title, u.created_at
  from auth.users u
  left join public.admins a on a.user_id = u.id
  left join public.roles r on r.name = a.role
  where public.has_admin_perm('admins')
  order by u.created_at;
$$;

-- Выдать роль по user_id (из списка). Сам подтягивает и сохраняет email аккаунта.
create or replace function public.set_admin_role_by_id(_user_id uuid, _role text, _status text default 'active', _display_name text default null)
returns void language plpgsql security definer set search_path = public as $$
declare actor_role text := public.current_admin_role(); target_old public.admins%rowtype; _email text;
begin
  if not public.has_admin_perm('admins') then raise exception 'Недостаточно прав'; end if;
  if not exists (select 1 from public.roles where name = _role) then raise exception 'Неизвестная роль: %', _role; end if;
  if actor_role <> 'owner' and _role in ('owner','admin') then raise exception 'Только главный админ может выдавать админа'; end if;
  if not exists (select 1 from auth.users where id = _user_id) then raise exception 'Пользователь не найден'; end if;
  select email into _email from auth.users where id = _user_id;
  select * into target_old from public.admins where user_id = _user_id;
  if found and target_old.protected and actor_role <> 'owner' then raise exception 'Защищённую учётку меняет только главный админ'; end if;
  if found and target_old.role = 'owner' and actor_role <> 'owner' then raise exception 'Главного админа меняет только он сам'; end if;
  insert into public.admins (user_id, email, display_name, role, status, protected, updated_at, updated_by)
  values (_user_id, lower(_email), nullif(_display_name,''), _role, coalesce(nullif(_status,''),'active'),
          case when _role='owner' then true else false end, now(), auth.uid())
  on conflict (user_id) do update set
    email = excluded.email,
    display_name = coalesce(excluded.display_name, public.admins.display_name),
    role = excluded.role, status = excluded.status, updated_at = now(), updated_by = auth.uid();
end; $$;

-- Публичные бейджи ролей для персонала: только Discord-имя + роль (не email/id).
-- Доступно всем (anon) — сайт показывает бейдж «Админ/Модератор/...» на карточке.
create or replace function public.public_staff_roles()
returns table (discord text, role text, role_title text, level int)
language sql stable security definer set search_path = public as $$
  select coalesce(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name',
                  u.raw_user_meta_data->>'user_name', u.raw_user_meta_data->>'preferred_username') as discord,
         a.role, r.title, r.role_level
  from public.admins a
  join auth.users u on u.id = a.user_id
  left join public.roles r on r.name = a.role
  where a.status = 'active' and a.role in ('owner','admin','moderator','helper');
$$;

grant execute on function public.list_site_users()                       to authenticated;
grant execute on function public.set_admin_role_by_id(uuid,text,text,text) to authenticated;
grant execute on function public.public_staff_roles()                    to anon, authenticated;
