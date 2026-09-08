# 📰 가좌버핏 뉴스

매일 발행되는 주요 경제·산업·국제 뉴스 요약 아카이브입니다.

🌐 **사이트 보기**: https://[본인깃허브아이디].github.io/daily-news/

---

## 📂 폴더 구조

```
daily-news/
├── index.html              ← 메인 페이지 (아카이브 목록)
├── archive/
│   └── 2026-04-28.html     ← 일자별 발행분
└── README.md
```

---

## 📅 새 뉴스레터 추가하는 방법

### 1단계: 일자별 HTML 파일 업로드
- 새 발행분 HTML 파일을 받으면 파일명을 `YYYY-MM-DD.html` 형식으로 저장
  - 예: `2026-04-29.html`
- 저장소 → `archive` 폴더 → `Add file` → `Upload files`로 업로드

### 2단계: 메인 페이지(index.html) 업데이트
`index.html` 파일을 편집해서 다음 두 부분을 수정합니다:

#### ① 최신호 카드 업데이트 (12~22행 근처)
```html
<a href="archive/2026-04-29.html" class="latest-card">
    <div class="date-big">2026.04.29</div>
    <div class="day-name">수요일 · N개 기사</div>
    <div class="preview">
        새 발행분 미리보기 텍스트
    </div>
    ...
</a>
```

#### ② 아카이브 목록에 새 항목 추가
`<!-- ★★★ 새 발행분 추가 시 여기에 복사해서 사용 ★★★ -->` 주석 부분의 템플릿을 복사해서 붙여넣고, 날짜와 내용을 수정합니다.

---

## 🛠️ 더 편한 방법: GitHub Desktop

웹에서 매번 편집하기 번거로우면 [GitHub Desktop](https://desktop.github.com/) 설치를 추천합니다.

1. 저장소를 PC에 클론
2. 새 파일을 폴더에 넣기
3. 커밋 메시지 입력 후 Push 버튼 한 번

---

## 📝 라이선스

본 프로젝트는 개인 학습 및 기록 목적으로 작성되었습니다.
원문 신문 기사의 저작권은 각 언론사에 있습니다.

---

## 👤 회원 로그인 켜기 (Supabase · 구글 로그인)

ETF 검색기의 컨센서스 구간은 로그인한 회원에게만 보입니다. 아래 순서대로 한 번만 설정하면 됩니다.
코드는 이미 들어 있고, 마지막에 값 두 개만 채우면 켜집니다.

### 1) Supabase 프로젝트 — 이미 있음 (건너뜀)
좋아요 집계에 쓰는 `gjbuffet-news` 프로젝트를 그대로 씁니다. `assets/auth-config.js` 에 주소·키가 이미 들어 있습니다.

### (참고) 새 프로젝트를 만들 때
1. https://supabase.com 가입 → **New project**
2. 이름 `gjbuffet`, Region은 **Northeast Asia (Seoul)**, 데이터베이스 비밀번호는 아무 곳에 적어두기
3. 만들어지면 **Project Settings → API** 화면을 열어둔다 (여기 값이 4단계에 필요)

### 2) 구글 로그인 연결
1. https://console.cloud.google.com → 새 프로젝트(이름 `gjbuffet`)
2. **API 및 서비스 → OAuth 동의 화면**: 외부(External), 앱 이름 `가좌버핏`, 지원 이메일 입력, 승인된 도메인에 `gjbuffet.kr` 과 `supabase.co` 추가 → 저장
3. **사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**: 유형 **웹 애플리케이션**
   - 승인된 리디렉션 URI: `https://ujpelcnigrryjprztzhf.supabase.co/auth/v1/callback`
     (Supabase → Authentication → Providers → Google 화면에 "Callback URL"로 표시됨)
4. 발급된 **클라이언트 ID / 클라이언트 보안 비밀**을 복사
5. Supabase → **Authentication → Providers → Google** 켜고 두 값을 붙여넣기 → Save

### 3) 돌아올 주소 허용
Supabase → **Authentication → URL Configuration**
- Site URL: `https://gjbuffet.kr`
- Redirect URLs: `https://gjbuffet.kr/**`

### 4) 사이트에 값 넣기 — 이미 채워져 있음
`assets/auth-config.js` 에 값이 들어 있습니다. 프로젝트를 바꿀 때만 고치면 됩니다.
```js
window.GJ_AUTH = {
  url: 'https://xxxxxxxxxxxx.supabase.co',   // Project Settings → API → Project URL
  anonKey: 'eyJhbGciOi...'                    // Project Settings → API → anon public
};
```
`anon public` 키는 브라우저에 공개되도록 만들어진 키라 저장소에 넣어도 됩니다.
**`service_role` 키는 절대 넣지 마세요.**

### 5) 확인
`gjbuffet.kr/tools/etf/` 기준일 줄 오른쪽에 **로그인** 버튼이 보이면 완료.
("로그인 준비 중"으로 보이면 4단계 값이 아직 비어 있는 것)

회원 명단은 Supabase → **Authentication → Users** 에서 볼 수 있습니다.

---

## ⚙️ 관리자 페이지 (`/admin/`)

회원 역할(마스터·관리자·부관리자)과 종목 조회 통계를 보는 화면입니다. 한 번만 준비하면 됩니다.

1. `supabase/001_admin.sql` 파일 내용을 전부 복사
2. https://supabase.com/dashboard/project/ujpelcnigrryjprztzhf/sql/new 에 붙여넣고 **Run**
3. `gjbuffet.kr/admin/` 을 마스터 계정(tyannytyanny@gmail.com)으로 열기

역할 규칙
- **마스터**: 관리자·부관리자 지정/해제, 통계 열람. 마스터는 SQL 로만 바꿀 수 있음
- **관리자**: 부관리자 지정/해제, 통계 열람
- **부관리자**: 통계 열람만

조회 기록은 로그인한 회원이 ETF 검색기에서 종목·ETF 상세를 열 때 남습니다 (같은 화면 5분 내 재조회는 1건).
