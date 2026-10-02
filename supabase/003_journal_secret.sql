-- =====================================================================
-- 매매 복기 암호문(admin/data/journal.enc.json)을 푸는 개인키 보관함
--   (Supabase SQL Editor 에 붙여넣고 Run · 여러 번 실행해도 안전)
--   마스터 계정(tyannytyanny@gmail.com) 본인만 읽을 수 있습니다. 화면에서 쓰기·수정은 불가.
--   002_trade_journal.sql 의 is_journal_owner() 를 사용하므로 002 를 먼저 실행해야 합니다.
--
--   ⚠️ 실제 개인키 값은 이 파일(공개 저장소)에 절대 넣지 않습니다.
--      아래 '<<개인키 JSON>>' 자리에 Claude 가 채팅으로 알려준 값을 넣어 실행하세요.
-- =====================================================================

create table if not exists public.journal_secret (
  id          smallint primary key default 1 check (id = 1),
  private_jwk text not null,
  updated_at  timestamptz not null default now()
);
alter table public.journal_secret enable row level security;

drop policy if exists "journal_secret_select" on public.journal_secret;
create policy "journal_secret_select" on public.journal_secret
  for select to authenticated using (public.is_journal_owner());

revoke all on public.journal_secret from anon, authenticated;
grant select on public.journal_secret to authenticated;

insert into public.journal_secret (id, private_jwk) values (1, '<<개인키 JSON>>')
on conflict (id) do update set private_jwk = excluded.private_jwk, updated_at = now();
