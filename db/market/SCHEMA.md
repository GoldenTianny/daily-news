# 시장 데이터 DB (db/market/)

수정주가·목표주가 컨센서스 시계열. **월별 Parquet 파일**(YYYY-MM.parquet)로 저장됩니다.

> **일일 갱신은 한 줄로**: `python3 tools/ingest_daily.py <원본.xlsx>` — 기준일을 자동 인식해 ETF·수정주가·컨센서스·영업이익 컨센서스·RS 등급·신고가 분석·미너비니 템플릿을 순서대로 갱신합니다. 아래는 개별 단계 설명.

- 원천: HTS 다운로드 엑셀 `ETF_price_concensus_YYYYMMDD.xlsx` (시트: `수정주가`, `consencus` — `ETF raw` 시트는 `tools/etf/build_data.py` 담당)
- 생성: `python3 tools/market/build_market.py <원본.xlsx>` — 원본에 담긴 날짜만 교체하고 나머지는 유지(병합)하므로, 짧은 기간(예: 최근 2일)만 담긴 일일 원본을 올려도 과거 데이터가 지워지지 않음. 내용이 같은 달은 건너뜀
- 이후 `python3 tools/market/build_rs.py`를 실행해 RS 등급(`db/market/rs/`)을 갱신
- 압축: SNAPPY

## db/market/price/ — 수정주가

일별 수정주가(액면분할·배당 등 반영). 일반 종목과 ETF를 모두 포함합니다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DATE | 거래일 |
| `code` | VARCHAR | 종목코드 (예: A005930) — `db/etf/`의 `etf_code`와 같은 체계 |
| `name` | VARCHAR | 종목명 |
| `close` | DOUBLE | 수정주가(원) |

- 범위: 2024-08-14 ~ (업로드 시점 전 영업일), 약 4,200개 종목·ETF
- 규모: 월당 약 7만~8만 행, 파일당 약 500KB

## db/market/consensus/ — 목표주가 컨센서스

애널리스트 목표주가 평균. 커버리지가 있는 종목(약 670개)만 값이 존재합니다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DATE | 기준일 |
| `code` | VARCHAR | 종목코드 |
| `name` | VARCHAR | 종목명 |
| `target_price` | DOUBLE | 목표주가(원) |

- 범위: 2025-08-14 ~ (업로드일), 파일당 약 40KB

## db/market/rs/ — 오닐식 RS 등급

각 거래일 기준 상대강도 등급(1~99). `tools/market/build_rs.py`가 수정주가 DB에서 계산합니다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DATE | 기준일 |
| `code` | VARCHAR | 종목코드 |
| `name` | VARCHAR | 종목명 |
| `rs` | UTINYINT | RS 등급 1~99 (99=최상위) |

- 산식: 최근 4개 분기 수익률(거래일 63/126/189/252 기준)을 **40/20/20/20 가중**한 점수의 백분위 순위
- 모집단: **일반 종목만** — ETF는 종목 조합의 복제라 순위 모집단에서 제외하되, 자기 점수가 일반 종목 분포에서 차지하는 백분위로 등급 부여 (예: ETF 등급 90 = 일반 종목 상위 10% 성과. ETF 코드는 `db/etf/`에서 추출)
- 252거래일 이력이 있는 날짜·종목만 포함 (신규 상장은 1년 후부터 등급 부여)
- 범위: 2025-09 ~ (가격 DB 시작일 + 1년), 월당 약 7만 행·250KB
- 갱신: `python3 tools/market/build_rs.py` — 미계산 날짜만 추가하므로 일일 실행은 수 초

## db/market/earnings/ — 연간 영업이익 실적·컨센서스

원본 `concensus_for_db*.xlsx` (시트: `fixed` 확정 실적, `YYYY annual margin` 컨센서스 추이).
`python3 tools/market/build_earnings.py <원본.xlsx>` 로 갱신 (ingest_daily.py가 시트 구성으로 자동 인식).

**annual.parquet** — 회계연도별 영업이익 (단위: 천원)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `code` / `name` | VARCHAR | 종목코드 / 종목명(가격 DB 명칭으로 정규화) |
| `fy` | SMALLINT | 회계연도 |
| `op` | DOUBLE | 영업이익(천원) |
| `src` | VARCHAR | 'A' 확정 실적 / 'E' 최신 컨센서스 |

- 확정(A)은 2019~, 4분기 실적 확정 시 해당 연도가 자동 추가됨 (fixed 시트의 AS 컬럼 기준)
- 컨센서스(E)는 확정이 없는 연도만 수록 (현재 2026·2027)

**consensus/YYYY-MM.parquet** — 연간 컨센서스의 일별 추이 (date, code, name, fy, op).
날짜 단위 병합이라 짧은 기간 원본을 올려도 과거가 유지됨. Base Date가 날짜가 아닌 컬럼('CPD-1TD')은 제외.

- 소비처: ETF 검색기 종목 화면의 "연도별 영업이익 증가율" 카드 (E 연도 클릭 시 추이 차트)

## db/market/minervini/ — 미너비니 트렌드 템플릿 판정

마크 미너비니의 '트렌드 템플릿' 8개 조건을 매 거래일 종목별로 판정. `tools/market/build_minervini.py`가 수정주가·RS DB에서 계산합니다 (ingest_daily 6단계).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` / `code` / `name` | | 기준일 / 종목코드 / 종목명 |
| `close` | DOUBLE | 종가(원) |
| `rs` | UTINYINT | 그날의 RS 등급 (없으면 NULL → 조건 8 미충족) |
| `ma50` / `ma150` / `ma200` | DOUBLE | 종가 이동평균 (거래일 창) |
| `hi52` / `lo52` | DOUBLE | 252거래일 종가 최고 / 최저 |
| `flags` | UTINYINT | 비트 i-1 = 조건 i 충족 (예: 255 = 8개 모두) |
| `pass_n` | UTINYINT | 충족 조건 수 (0~8) |
| `passed` | BOOLEAN | 8개 모두 충족 |
| `streak` | USMALLINT | 연속 충족 거래일 수 (미충족이면 0) |
| `n_univ` | USMALLINT | 그날 판정한 모집단 종목 수 |

- 조건: ① 종가 > 150·200일선 ② 150일선 > 200일선 ③ 200일선이 21거래일 전보다 상승 ④ 50일선 > 150·200일선 ⑤ 종가 > 50일선 ⑥ 52주 저점 대비 +30% 이상 ⑦ 52주 고점 대비 −25% 이내 ⑧ RS 70 이상
- 모집단: 일반 종목만 (`tools/study/build_high52.universe_filter` — ETF·ETN·스팩·우선주·동전주 제외), 260거래일 이상 이력 필요
- **저장은 6개 이상 충족 종목만** (충족 + 근접). streak는 전 종목으로 계산한 뒤 걸러 저장. 월당 약 7천 행·150KB
- 소비처: `tools/etf/minervini.html` (최신 월 파일의 마지막 날짜)

## 쿼리 예시 (DuckDB)

```python
import duckdb

# 종가 대비 목표주가 괴리율
duckdb.sql("""
  SELECT p.date, p.name, p.close, c.target_price,
         ROUND((c.target_price/p.close - 1)*100, 1) AS upside_pct
  FROM 'db/market/price/*.parquet' p
  JOIN 'db/market/consensus/*.parquet' c USING(date, code)
  WHERE p.name = 'SK하이닉스' ORDER BY p.date DESC LIMIT 5
""")

# ETF 보유내역(db/etf/)과 결합해 종목별 수익률 가중 분석도 가능
# (조인 키: price.code = etf.etf_code 또는 name 매칭)
```

## 유의

- 값이 없는 셀(거래정지·미커버리지 등)은 행 자체가 없습니다
- 수정주가는 이벤트(분할 등) 발생 시 과거치가 소급 변경될 수 있어, 재업로드 시 과거 월 파일도 갱신될 수 있습니다 (build_market.py가 자동 감지)
- 컨센서스 최신일은 업로드 당일(CPD)까지 포함되어 price보다 하루 앞설 수 있습니다
