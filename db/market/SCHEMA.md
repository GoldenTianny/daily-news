# 시장 데이터 DB (db/market/)

수정주가·목표주가 컨센서스 시계열. **월별 Parquet 파일**(YYYY-MM.parquet)로 저장됩니다.

> **일일 갱신은 한 줄로**: `python3 tools/ingest_daily.py <원본.xlsx>` — 기준일을 자동 인식해 ETF·수정주가·컨센서스·RS 등급을 순서대로 갱신합니다. 아래는 개별 단계 설명.

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
- 모집단: **ETF와 일반 종목을 분리**해 각각 순위 산정 (ETF 코드는 `db/etf/`에서 추출)
- 252거래일 이력이 있는 날짜·종목만 포함 (신규 상장은 1년 후부터 등급 부여)
- 범위: 2025-09 ~ (가격 DB 시작일 + 1년), 월당 약 7만 행·250KB
- 갱신: `python3 tools/market/build_rs.py` — 미계산 날짜만 추가하므로 일일 실행은 수 초

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
