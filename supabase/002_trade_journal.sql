-- =====================================================================
-- 매매 복기(체결내역) 저장소  (Supabase SQL Editor 에 통째로 붙여넣고 Run)
--   실행 주소: https://supabase.com/dashboard/project/ujpelcnigrryjprztzhf/sql/new
--   여러 번 실행해도 안전합니다.
--   마스터 계정(tyannytyanny@gmail.com) 본인만 읽고 쓸 수 있습니다.
--   관리자·부관리자·다른 회원·비회원은 행 자체가 보이지 않습니다.
-- =====================================================================

create table if not exists public.trade_journal (
  owner      uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  raw        text not null,
  file_name  text,
  updated_at timestamptz not null default now()
);
alter table public.trade_journal enable row level security;

-- 로그인한 계정이 매매 복기 주인인지 (auth.users 의 실제 이메일로 확인)
create or replace function public.is_journal_owner()
returns boolean language sql stable security definer set search_path = public, auth as $$
  select coalesce((select lower(email) = 'tyannytyanny@gmail.com' from auth.users where id = auth.uid()), false)
$$;

drop policy if exists "journal_select" on public.trade_journal;
drop policy if exists "journal_insert" on public.trade_journal;
drop policy if exists "journal_update" on public.trade_journal;
drop policy if exists "journal_delete" on public.trade_journal;
create policy "journal_select" on public.trade_journal
  for select to authenticated using (owner = auth.uid() and public.is_journal_owner());
create policy "journal_insert" on public.trade_journal
  for insert to authenticated with check (owner = auth.uid() and public.is_journal_owner());
create policy "journal_update" on public.trade_journal
  for update to authenticated using (owner = auth.uid() and public.is_journal_owner())
  with check (owner = auth.uid() and public.is_journal_owner());
create policy "journal_delete" on public.trade_journal
  for delete to authenticated using (owner = auth.uid() and public.is_journal_owner());

revoke all on public.trade_journal from anon;
grant select, insert, update, delete on public.trade_journal to authenticated;
