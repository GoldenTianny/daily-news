-- =====================================================================
-- 가좌버핏 회원 역할 + 종목 조회 통계  (Supabase SQL Editor 에 통째로 붙여넣고 Run)
--   실행 주소: https://supabase.com/dashboard/project/ujpelcnigrryjprztzhf/sql/new
--   여러 번 실행해도 안전합니다 (있으면 건너뜀).
-- =====================================================================

-- 1) 회원 프로필 (auth.users 와 1:1) --------------------------------------
create table if not exists public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text,
  name       text,
  role       text not null default 'member' check (role in ('master','admin','sub','member')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.profiles enable row level security;

-- 아직 가입하지 않은 사람을 이메일로 미리 관리자/부관리자 지정 (가입 순간 적용 후 삭제)
create table if not exists public.role_grants (
  email      text primary key,
  role       text not null check (role in ('admin','sub')),
  granted_by uuid,
  created_at timestamptz not null default now()
);
alter table public.role_grants enable row level security;

-- 가입하면 자동으로 프로필 생성. 마스터 이메일은 master 로, 미리 지정된 이메일은 그 역할로.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare granted text;
begin
  select role into granted from public.role_grants where email = lower(new.email);
  insert into public.profiles (id, email, name, role)
  values (
    new.id, new.email,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', split_part(coalesce(new.email,''),'@',1)),
    case when lower(new.email) = 'tyannytyanny@gmail.com' then 'master' else coalesce(granted, 'member') end
  )
  on conflict (id) do update set email = excluded.email, name = excluded.name, updated_at = now();
  if granted is not null then delete from public.role_grants where email = lower(new.email); end if;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 이미 가입한 회원 채워넣기 + 마스터 지정
insert into public.profiles (id, email, name, role)
select id, email,
       coalesce(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name', split_part(coalesce(email,''),'@',1)),
       case when lower(email) = 'tyannytyanny@gmail.com' then 'master' else 'member' end
from auth.users
on conflict (id) do nothing;

update public.profiles set role = 'master', updated_at = now()
where lower(email) = 'tyannytyanny@gmail.com';

-- 역할 확인 도우미
create or replace function public.my_role()
returns text language sql stable security definer set search_path = public as $$
  select role from public.profiles where id = auth.uid()
$$;

create or replace function public.is_staff()
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce((select role in ('master','admin','sub') from public.profiles where id = auth.uid()), false)
$$;

-- 읽기: 본인 것은 누구나, 전체는 관리자(master/admin/sub)만. 역할 변경은 아래 RPC 로만.
drop policy if exists "profiles_read" on public.profiles;
create policy "profiles_read" on public.profiles
  for select to authenticated using (id = auth.uid() or public.is_staff());

drop policy if exists "grants_read_staff" on public.role_grants;
create policy "grants_read_staff" on public.role_grants
  for select to authenticated using (public.is_staff());

-- 역할 변경 규칙
--   master : 누구든 admin / sub / member 로 변경 (단 master 본인은 불변)
--   admin  : sub <-> member 만 변경 (admin 지정·해제는 master 만)
--   sub    : 변경 불가
create or replace function public.admin_set_role(target uuid, new_role text)
returns void language plpgsql security definer set search_path = public as $$
declare me text; tgt text;
begin
  select role into me  from public.profiles where id = auth.uid();
  select role into tgt from public.profiles where id = target;
  if tgt is null then raise exception '대상 회원이 없습니다'; end if;
  if new_role not in ('admin','sub','member') then raise exception '지정할 수 없는 역할입니다'; end if;
  if tgt = 'master' then raise exception '마스터 관리자는 변경할 수 없습니다'; end if;
  if me = 'master' then
    null;
  elsif me = 'admin' then
    if new_role = 'admin' or tgt = 'admin' then
      raise exception '관리자 지정·해제는 마스터만 할 수 있습니다';
    end if;
  else
    raise exception '권한이 없습니다';
  end if;
  update public.profiles set role = new_role, updated_at = now() where id = target;
end $$;

-- 이메일로 지정: 이미 가입한 회원이면 즉시 적용('applied'), 아니면 예약('pending')
create or replace function public.admin_grant_by_email(p_email text, new_role text)
returns text language plpgsql security definer set search_path = public as $$
declare me text; em text; tid uuid; tgt text;
begin
  select role into me from public.profiles where id = auth.uid();
  em := lower(trim(p_email));
  if em !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception '이메일 형식이 아닙니다'; end if;
  if new_role not in ('admin','sub') then raise exception '지정할 수 없는 역할입니다'; end if;
  if me = 'master' then null;
  elsif me = 'admin' then
    if new_role = 'admin' then raise exception '관리자 지정은 마스터만 할 수 있습니다'; end if;
  else raise exception '권한이 없습니다'; end if;

  select id, role into tid, tgt from public.profiles where lower(email) = em;
  if tid is not null then
    if tgt = 'master' then raise exception '마스터 관리자는 변경할 수 없습니다'; end if;
    if me = 'admin' and tgt = 'admin' then raise exception '관리자 변경은 마스터만 할 수 있습니다'; end if;
    update public.profiles set role = new_role, updated_at = now() where id = tid;
    delete from public.role_grants where email = em;
    return 'applied';
  end if;
  insert into public.role_grants (email, role, granted_by) values (em, new_role, auth.uid())
  on conflict (email) do update set role = excluded.role, granted_by = excluded.granted_by, created_at = now();
  return 'pending';
end $$;

-- 예약 취소
create or replace function public.admin_revoke_grant(p_email text)
returns void language plpgsql security definer set search_path = public as $$
declare me text; r text;
begin
  select role into me from public.profiles where id = auth.uid();
  select role into r from public.role_grants where email = lower(trim(p_email));
  if r is null then return; end if;
  if me = 'master' then null;
  elsif me = 'admin' then
    if r = 'admin' then raise exception '관리자 예약 취소는 마스터만 할 수 있습니다'; end if;
  else raise exception '권한이 없습니다'; end if;
  delete from public.role_grants where email = lower(trim(p_email));
end $$;

-- 2) 종목 조회 기록 ---------------------------------------------------------
create table if not exists public.stock_views (
  id        bigint generated always as identity primary key,
  user_id   uuid references auth.users(id) on delete cascade,   -- 비회원이면 null
  anon_id   text,                                                -- 비회원 브라우저 식별자 (좋아요와 같은 gjb_fp)
  view_type text not null default 'stock' check (view_type in ('stock','etf')),
  name      text not null,
  code      text,
  base_date date,                              -- 화면에서 보고 있던 기준일
  viewed_at timestamptz not null default now() -- 실제 조회 시각
);
create index if not exists stock_views_base_idx on public.stock_views (base_date, view_type, name);
create index if not exists stock_views_time_idx on public.stock_views (viewed_at);
create index if not exists stock_views_user_idx on public.stock_views (user_id, viewed_at);
alter table public.stock_views enable row level security;

-- 이미 만들어진 표 업그레이드 (여러 번 실행해도 안전)
alter table public.stock_views alter column user_id drop not null;
alter table public.stock_views add column if not exists anon_id text;

drop policy if exists "views_insert_own" on public.stock_views;
create policy "views_insert_own" on public.stock_views
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists "views_insert_guest" on public.stock_views;
create policy "views_insert_guest" on public.stock_views
  for insert to anon with check (user_id is null and anon_id is not null);

drop policy if exists "views_read_staff" on public.stock_views;
create policy "views_read_staff" on public.stock_views
  for select to authenticated using (public.is_staff());

-- 통계 1: 날짜 × 종목  (by_view_date = true 면 '조회한 날' 기준, false 면 '보던 기준일' 기준)
--   who = 'all' | 'member' | 'guest'
--   vtype = 'all' | 'stock' | 'etf'
drop function if exists public.admin_view_stats(date, date, text, boolean);
drop function if exists public.admin_view_stats(date, date, text, boolean, text);
create or replace function public.admin_view_stats(d_from date, d_to date, vtype text default 'all', by_view_date boolean default false, who text default 'all')
returns table (d date, view_type text, name text, code text, views bigint, member_views bigint, guest_views bigint, users bigint, guests bigint, last_at timestamptz)
language sql stable security definer set search_path = public as $$
  select case when by_view_date then (viewed_at at time zone 'Asia/Seoul')::date else base_date end as d,
         view_type, name, max(code),
         count(*),
         count(*) filter (where user_id is not null),
         count(*) filter (where user_id is null),
         count(distinct user_id),
         count(distinct anon_id) filter (where user_id is null),
         max(viewed_at)
  from public.stock_views
  where public.is_staff()
    and (vtype = 'all' or view_type = vtype)
    and (user_id is null or user_id not in (select id from public.profiles where role in ('master','admin','sub')))   -- 운영진 제외
    and (who = 'all' or (who = 'member' and user_id is not null) or (who = 'guest' and user_id is null))
    and (case when by_view_date then (viewed_at at time zone 'Asia/Seoul')::date else base_date end) between d_from and d_to
  group by 1, 2, 3
  order by 1 desc, 5 desc
$$;

-- 통계 2: 회원별
create or replace function public.admin_user_stats(d_from date, d_to date)
returns table (user_id uuid, email text, name text, role text, views bigint, stocks bigint, last_at timestamptz)
language sql stable security definer set search_path = public as $$
  select p.id, p.email, p.name, p.role, count(v.id), count(distinct v.name), max(v.viewed_at)
  from public.profiles p
  left join public.stock_views v
    on v.user_id = p.id and (v.viewed_at at time zone 'Asia/Seoul')::date between d_from and d_to
  where public.is_staff() and p.role = 'member'   -- 운영진(마스터·관리자·부관리자) 제외
  group by p.id, p.email, p.name, p.role
  order by count(v.id) desc, p.created_at desc
$$;

-- 통계 3: 최근 조회 원본 (마지막 N건) — 비회원은 email null, anon 은 브라우저 식별자 앞 6자리
drop function if exists public.admin_recent_views(int);
create or replace function public.admin_recent_views(n int default 200)
returns table (viewed_at timestamptz, email text, anon text, name text, view_type text, base_date date)
language sql stable security definer set search_path = public as $$
  select v.viewed_at, p.email, left(v.anon_id, 6), v.name, v.view_type, v.base_date
  from public.stock_views v left join public.profiles p on p.id = v.user_id
  where public.is_staff() and coalesce(p.role, 'member') = 'member'   -- 운영진 제외
  order by v.viewed_at desc
  limit greatest(1, least(n, 1000))
$$;

-- 통계 4: 기간 요약 (회원/비회원 조회 수와 사람 수)
create or replace function public.admin_view_summary(d_from date, d_to date, vtype text default 'all', by_view_date boolean default false)
returns table (views bigint, member_views bigint, guest_views bigint, users bigint, guests bigint, names bigint)
language sql stable security definer set search_path = public as $$
  select count(*),
         count(*) filter (where user_id is not null),
         count(*) filter (where user_id is null),
         count(distinct user_id),
         count(distinct anon_id) filter (where user_id is null),
         count(distinct name)
  from public.stock_views
  where public.is_staff()
    and (vtype = 'all' or view_type = vtype)
    and (user_id is null or user_id not in (select id from public.profiles where role in ('master','admin','sub')))   -- 운영진 제외
    and (case when by_view_date then (viewed_at at time zone 'Asia/Seoul')::date else base_date end) between d_from and d_to
$$;
