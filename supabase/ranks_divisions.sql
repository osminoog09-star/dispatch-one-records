-- ============================================================
--  Звания по отделам: у каждого звания появляется division (department_id).
--  Анализ структуры LAPD:
--   • Командование (без отдела, общедепартаментские): Watch Commander, Lieutenant,
--     Sergeant II, Sergeant I
--   • Detective Division: Detective III / II / I
--   • Patrol Division LAPD: Officer III / II / I, Rookie
--   • Training Division LAPD: Head of the training program, Field Training Officer [FTO]
--   • METRO / AIR-unit: своих званий нет (сотрудники сохраняют звание)
--   • Статусы (без отдела, по сути не звания): Distinguished officer, Acting,
--     Vacation, Candidate, Visitor
--   • Supervisor — это ДОЛЖНОСТЬ (начальник смены), не звание → таблица positions
-- ============================================================

alter table public.ranks add column if not exists department_id int
  references public.departments(id) on delete set null;

-- привязка званий к отделам (по названию, чтобы не зависеть от id)
update public.ranks r set department_id = d.id
  from public.departments d
  where d.name = 'Detective Division' and r.name in ('Detective III','Detective II','Detective I');

update public.ranks r set department_id = d.id
  from public.departments d
  where d.name = 'Patrol Division LAPD' and r.name in ('Officer III','Officer II','Officer I','Rookie');

update public.ranks r set department_id = d.id
  from public.departments d
  where d.name = 'Training Division LAPD'
    and r.name in ('Head of the training program','Field Training Officer [FTO]');

-- на всякий случай убедимся, что нужные отделы есть (id не важен, ищем по имени)
insert into public.departments (name, color, ord) values
 ('Detective Division','#8957e5',6)
 on conflict (name) do nothing;

-- ---- должности (positions): Supervisor = начальник смены и т.п. ----
create table if not exists public.positions (
  id serial primary key, name text unique not null, color text, ord int default 0);
alter table public.positions enable row level security;
drop policy if exists positions_read on public.positions;
create policy positions_read on public.positions for select using (true);
drop policy if exists positions_write on public.positions;
create policy positions_write on public.positions for all
  using (public.is_admin()) with check (public.is_admin());

alter table public.officer_profiles
  add column if not exists position_id int references public.positions(id) on delete set null;

insert into public.positions (name, color, ord) values
 ('Supervisor (начальник смены)','#e3b341',1)
 on conflict (name) do nothing;

-- Supervisor больше не звание — убираем из ranks (профили с ним обнулятся: FK set null)
delete from public.ranks where name = 'Supervisor';
