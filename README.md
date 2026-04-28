# 📰 Daily News Brief

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
