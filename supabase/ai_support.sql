-- ============================================================
--  LAPD Records — помощник поддержки.
--  ГЛАВНОЕ ПРАВИЛО: платный разбор запускается ТОЛЬКО по кнопке владельца.
--
--  Как это экономит деньги:
--    1) игрок сначала получает бесплатный разбор по правилам на /support;
--    2) если не помогло — жалоба уходит в очередь «заявок» (бесплатно) и там
--       копится: видно, что одна и та же ошибка уже у N человек;
--    3) владелец в /admin решает: ответить руками (бесплатно) или нажать
--       «Разобрать помощником» — только этот клик тратит платный запрос;
--    4) ответ ложится в кеш и дальше раздаётся всем с такой же ошибкой даром;
--    5) сверху дневной лимит-страховка и общий выключатель.
--
--  Запусти в Supabase → SQL Editor → Run. Идемпотентно. Уже применено 2026-08-13.
-- ============================================================

create table if not exists public.ai_settings (
  id int primary key default 1,
  enabled boolean not null default true,
  daily_limit int not null default 20,          -- страховка на случай ошибки в UI
  updated_by text,
  updated_at timestamptz default now(),
  constraint ai_settings_single_row check (id = 1)
);
insert into public.ai_settings (id) values (1) on conflict (id) do nothing;

-- готовые ответы: раздаются бесплатно всем с такой же ошибкой
create table if not exists public.ai_cache (
  key text primary key,
  answer text not null,
  hits int not null default 0,
  created_at timestamptz default now()
);

-- заявки на разбор: копятся бесплатно, пока владелец не решит
create table if not exists public.ai_requests (
  key text primary key,
  sample text not null,          -- вырезка лога без секретов, до 4000 символов
  title text,
  count int not null default 1,  -- сколько раз эта ошибка встретилась
  status text not null default 'pending',   -- pending / answered / rejected
  answer text,
  first_seen timestamptz default now(),
  last_seen timestamptz default now(),
  decided_by text,
  decided_at timestamptz
);

create table if not exists public.ai_usage (
  day date primary key default current_date,
  used int not null default 0,   -- платных разборов
  saved int not null default 0   -- отдано из кеша (сэкономлено)
);

alter table public.ai_settings enable row level security;
alter table public.ai_cache    enable row level security;
alter table public.ai_requests enable row level security;
alter table public.ai_usage    enable row level security;

drop policy if exists ai_settings_read on public.ai_settings;
create policy ai_settings_read on public.ai_settings for select using (true);
drop policy if exists ai_cache_read on public.ai_cache;
create policy ai_cache_read on public.ai_cache for select using (true);
drop policy if exists ai_usage_read on public.ai_usage;
create policy ai_usage_read on public.ai_usage for select using (true);
-- заявки видит только тот, кто может ими управлять
drop policy if exists ai_requests_read on public.ai_requests;
create policy ai_requests_read on public.ai_requests for select using (public.can_manage_staff());

-- Игрок сообщает о проблеме. Бесплатно: либо сразу отдаём готовый ответ из кеша,
-- либо ставим заявку в очередь и увеличиваем счётчик повторов.
create or replace function public.ai_report_problem(_key text, _sample text, _title text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare a text; c int;
begin
  select answer into a from public.ai_cache where key = _key;
  if a is not null then
    update public.ai_cache set hits = hits + 1 where key = _key;
    insert into public.ai_usage (day, saved) values (current_date, 1)
      on conflict (day) do update set saved = public.ai_usage.saved + 1;
    return jsonb_build_object('answer', a, 'cached', true);
  end if;
  insert into public.ai_requests as r (key, sample, title)
  values (_key, left(_sample, 4000), _title)
  on conflict (key) do update set count = r.count + 1, last_seen = now();
  select count into c from public.ai_requests where key = _key;
  return jsonb_build_object('answer', null, 'queued', true, 'count', c);
end; $$;

-- Владелец разрешает платный разбор: проверяет выключатель и лимит, забирает
-- «талон» и отдаёт вырезку лога для отправки помощнику.
create or replace function public.ai_approve(_key text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare s public.ai_settings%rowtype; u int; smp text;
begin
  if not public.can_manage_staff() then raise exception 'нет прав'; end if;
  select * into s from public.ai_settings where id = 1;
  if not s.enabled then return jsonb_build_object('ok', false, 'reason', 'off'); end if;
  insert into public.ai_usage (day, used) values (current_date, 0) on conflict (day) do nothing;
  select used into u from public.ai_usage where day = current_date;
  if u >= s.daily_limit then return jsonb_build_object('ok', false, 'reason', 'limit'); end if;
  select sample into smp from public.ai_requests where key = _key;
  if smp is null then return jsonb_build_object('ok', false, 'reason', 'no_request'); end if;
  update public.ai_usage set used = used + 1 where day = current_date;
  return jsonb_build_object('ok', true, 'sample', smp, 'left', s.daily_limit - u - 1);
end; $$;

-- Сохранить ответ (написанный руками или полученный от помощника) — уходит в кеш.
create or replace function public.ai_save_answer(_key text, _answer text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.can_manage_staff() then raise exception 'нет прав'; end if;
  insert into public.ai_cache (key, answer) values (_key, _answer)
    on conflict (key) do update set answer = excluded.answer;
  update public.ai_requests set status = 'answered', answer = _answer,
    decided_by = coalesce(auth.jwt() ->> 'email','admin'), decided_at = now()
   where key = _key;
end; $$;

create or replace function public.ai_reject(_key text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.can_manage_staff() then raise exception 'нет прав'; end if;
  update public.ai_requests set status = 'rejected',
    decided_by = coalesce(auth.jwt() ->> 'email','admin'), decided_at = now()
   where key = _key;
end; $$;

create or replace function public.ai_stats()
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'enabled',     (select enabled from public.ai_settings where id = 1),
    'daily_limit', (select daily_limit from public.ai_settings where id = 1),
    'used_today',  coalesce((select used  from public.ai_usage where day = current_date), 0),
    'saved_today', coalesce((select saved from public.ai_usage where day = current_date), 0),
    'used_total',  coalesce((select sum(used)  from public.ai_usage), 0),
    'saved_total', coalesce((select sum(saved) from public.ai_usage), 0),
    'pending',     (select count(*) from public.ai_requests where status = 'pending'),
    'cached',      (select count(*) from public.ai_cache));
$$;

create or replace function public.ai_set_settings(_enabled boolean, _daily_limit int)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.can_manage_staff() then raise exception 'нет прав'; end if;
  update public.ai_settings set enabled = coalesce(_enabled, enabled),
    daily_limit = greatest(0, coalesce(_daily_limit, daily_limit)),
    updated_by = coalesce(auth.jwt() ->> 'email','admin'), updated_at = now()
   where id = 1;
end; $$;

grant execute on function public.ai_report_problem(text, text, text) to anon, authenticated;
grant execute on function public.ai_stats()                          to anon, authenticated;
grant execute on function public.ai_approve(text)                    to authenticated;
grant execute on function public.ai_save_answer(text, text)          to authenticated;
grant execute on function public.ai_reject(text)                     to authenticated;
grant execute on function public.ai_set_settings(boolean, int)       to authenticated;
