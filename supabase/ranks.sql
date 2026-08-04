-- ============================================================
--  Справочники LAPD: звания (полный список + цвета) и отделы.
--  Запусти в Supabase SQL Editor.
-- ============================================================

-- отделы (divisions)
create table if not exists public.departments (
  id serial primary key,
  name text unique not null,
  color text,
  ord int default 0
);
alter table public.departments enable row level security;
drop policy if exists departments_read on public.departments;
create policy departments_read on public.departments for select using (true);
drop policy if exists departments_write on public.departments;
create policy departments_write on public.departments for all
  using (public.is_admin()) with check (public.is_admin());

alter table public.officer_profiles
  add column if not exists department_id int references public.departments(id) on delete set null;

-- ---- звания: полный список (level = старшинство, выше = старше) ----
delete from public.ranks;
alter sequence public.ranks_id_seq restart with 1;
insert into public.ranks (name, abbr, level, color) values
 ('Watch Commander','WC',100,'#e3b341'),
 ('Lieutenant','Lt',95,'#e3b341'),
 ('Sergeant II','Sgt II',90,'#2f81f7'),
 ('Sergeant I','Sgt I',85,'#2f81f7'),
 ('Supervisor','Sup',80,'#e3b341'),
 ('Detective III','Det III',75,'#8957e5'),
 ('Detective II','Det II',70,'#8957e5'),
 ('Detective I','Det I',65,'#8957e5'),
 ('Head of the training program','HTP',60,'#2ea043'),
 ('Officer III','Off III',55,'#f85149'),
 ('Officer II','Off II',50,'#f85149'),
 ('Officer I','Off I',45,'#f85149'),
 ('Field Training Officer [FTO]','FTO',40,'#2ea043'),
 ('Rookie','Rk',35,'#2ea043'),
 ('Distinguished officer','Dist',30,'#f0883e'),
 ('Acting','Act',25,'#f85149'),
 ('Vacation','Vac',20,'#39c5cf'),
 ('Candidate','Cand',15,'#2f81f7'),
 ('Visitor','Vis',10,'#39c5cf');

-- ---- отделы ----
insert into public.departments (name, color, ord) values
 ('LAPD Detective','#8b949e',1),
 ('METRO Division','#8b949e',2),
 ('Patrol Division LAPD','#8b949e',3),
 ('AIR-unit LAPD','#8b949e',4),
 ('Training Division LAPD','#8b949e',5)
on conflict (name) do nothing;
