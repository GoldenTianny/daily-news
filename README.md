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

### 3단계: `sitemap.xml`에 새 발행분 추가 (검색 노출용)
구글 검색에 잘 잡히도록, 새 archive 파일을 올린 뒤 `sitemap.xml`에 아래 블록을 추가합니다.

```xml
<url>
  <loc>https://goldentianny.github.io/daily-news/archive/2026-04-30.html</loc>
  <lastmod>2026-04-30</lastmod>
  <changefreq>monthly</changefreq>
  <priority>0.8</priority>
</url>
```

루트(`/daily-news/`) URL의 `<lastmod>`도 오늘 날짜로 함께 갱신해 주세요.

---

## 🔎 검색(구글) 노출 설정

이 저장소에는 검색 색인을 돕는 파일들이 포함되어 있습니다.
- `robots.txt` — 크롤러 허용 + sitemap 위치 안내
- `sitemap.xml` — 전체 페이지 목록
- `index.html`과 archive 페이지에 canonical, Open Graph, JSON-LD 구조화 데이터 삽입

배포 후 한 번만 해두면 노출이 빨라지는 작업:
1. [Google Search Console](https://search.google.com/search-console) 에서 `https://goldentianny.github.io/daily-news/` 속성 등록
2. 인증을 메타태그 방식으로 받았다면, `index.html` 상단의 아래 주석을 풀고 코드 삽입
   ```html
   <!-- <meta name="google-site-verification" content="여기에-인증코드-붙여넣기"> -->
   ```
3. Search Console → Sitemaps 메뉴에서 `sitemap.xml` 제출
4. 새 발행분이 생기면 Search Console의 "URL 검사" 도구에서 색인 요청

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
