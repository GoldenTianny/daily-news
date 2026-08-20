# 가좌버핏 뉴스 (gjbuffet.kr)

빌드 도구 없는 **정적 사이트**. GitHub Pages가 `main` 브랜치를 그대로 서빙한다
(CI 워크플로 없음 — 푸시하면 곧 반영). HTML/CSS/JS는 각 페이지에 인라인으로
들어 있고, 파이썬 스크립트(`tools/`)가 데이터와 페이지를 생성한다.

## 구조

| 경로 | 내용 |
|---|---|
| `index.html` | 메인. 섹션별 최신 3건 카드를 **직접 하드코딩** |
| `archive/YYYY-MM-DD.html` | 일일 뉴스 브리프 (발행분) |
| `analysis/`, `companies/`, `book/` | 심층분석 · 기업분석 · 책리뷰. 파일명 `YYYY-MM-DD_슬러그.html` |
| `article/` | 좋은글 1,258편. `articles.json`(원본) → `p/<id>.html`(SEO 페이지) + `s/NN.html`(공유 stub) |
| `db/etf/YYYY-MM-DD.parquet` | 일자별 ETF 보유내역 |
| `db/market/{price,consensus,rs}/YYYY-MM.parquet` | 수정주가 · 컨센서스 · RS 등급 (월별) |
| `tools/` | 생성 스크립트 (아래) |
| `assets/og/` | OG 썸네일 PNG. `assets/fonts/`는 Pretendard |
| `stats/`, `console/`, `tools/etf/` | 통계 · 받아쓰기 콘솔 · ETF 검색기 (각각 독립 페이지) |

각 섹션 디렉터리에는 목록용 `index.html`이 따로 있다. **새 글을 추가하면
`index.html`(메인)과 해당 섹션의 `index.html` 두 곳을 모두 고쳐야 한다.**

## 매일 하는 작업 2가지

### 1) 일일브리프 발행

```bash
# tools/gen_market_section.py 상단 CONFIG(XLSX/DRAFT/PUB/OUT/BASE/PUB_DATE/GRAD)를 먼저 갱신
python3 tools/gen_market_section.py     # 초안 HTML의 시장 섹션을 기준일 종가로 재생성 → archive/YYYY-MM-DD.html
python3 tools/make_og.py archive/YYYY-MM-DD.html   # OG 썸네일 생성 + 해당 HTML의 og:image 메타 자동 갱신
```

그 다음 손으로: `index.html` 최신호 카드 + 뉴스 섹션 카드 추가, `archive/index.html`에 항목 추가.

`gen_market_section.py`는 **직전 발행본(`PUB`)에서 표 구조를 추출**하므로 `PUB`는 항상 최신 발행본을 가리켜야 한다.
CONFIG의 `TIPS`(6개)·`README_TEXTS`(7개)는 당일 데이터·뉴스 맥락으로 매번 새로 쓴다.

### 2) 시장 DB 갱신 (원본 엑셀 반영)

```bash
python3 tools/ingest_daily.py ~/Downloads/ETF_price_concensus_YYYYMMDD.xlsx
```

`build_data`(ETF 보유내역) → `build_market`(수정주가·컨센서스) → `build_rs`(RS 등급) 순으로
한 번에 돈다. 기준일은 'ETF raw' 시트에서 자동 인식하고, 실패하면 두 번째 인자로 `YYYY-MM-DD`를 준다.
개별 스크립트를 따로 부를 일은 거의 없다.

## 나머지 스크립트 (필요할 때만)

| 스크립트 | 언제 |
|---|---|
| `make_article_pages.py` | 좋은글 추가 후 → `article/p/*.html` + 루트 `sitemap.xml` 재생성 |
| `make_share_stubs.py` | `assets/og/article/NN.jpg` 사진 추가·교체 후 → 실행 뒤 `article/index.html`의 `STUB_COUNT`를 사진 개수에 맞출 것 |
| `make_og.py --all` | OG 썸네일 전체 재생성 |
| `make_etf_og.py` | ETF 검색기 OG(`assets/og/etf.png`)만 재생성 |
| `build_rs.py --all` | RS 등급 전체 재계산 (평소엔 새 날짜 1개만 증분 계산됨) |

## 알아둘 것

- **의존성**: `openpyxl`, `duckdb`, `pandas`, `Pillow`. 스크립트는 어느 디렉터리에서 실행해도 저장소 기준 경로로 동작한다.
- **parquet 직읽기**: ETF 검색기 웹은 `db/etf/*.parquet`를 hyparquet로 브라우저에서 직접 읽는다 (날짜별 JSON은 2026-08-11 폐지). 스키마를 바꾸면 `tools/etf/index.html`도 같이 봐야 한다.
- **git diff 최소화**: `build_market.py`는 내용이 같은 달 파일을 건너뛰고, `build_rs.py`는 계산된 날짜를 건너뛴다. 재실행해도 안전하다.
- **PWA**: 루트 `sw.js`는 네트워크 우선 + 캐시 폴백. 캐시 이름 `gjbuffet-v1`을 바꾸면 사용자 캐시가 전부 무효화된다.
- **`.gitignore`**: `article/*.txt`, `assets/quotes.json`, `assets/성공명언1001.md`는 각각 `articles.json`·HTML에 인라인 임베드되어 커밋하지 않는다.
- **`article/p/`, `article/s/`, `sitemap.xml`은 생성물**이다. 직접 고치지 말고 스크립트를 다시 돌린다.
- **커밋 메시지**: 한국어 한 줄 요약. 예) `8/20 일일브리프 발행 + 시장 대시보드 8/19 종가 반영`
