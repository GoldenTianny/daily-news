# 시장 데이터 DB (db/market/)

수정주가·목표주가 컨센서스 시계열. **월별 Parquet 파일**(YYYY-MM.parquet)로 저장됩니다.

- 원천: HTS 다운로드 엑셀 `ETF_price_concensus_YYYYMMDD.xlsx` (시트: `수정주가`, `consencus` — `ETF raw` 시트는 `tools/etf/build_data.py` 담당)
- 생성: `python3 tools/market/build_market.py <원본.xlsx>` — 원본에 담긴 날짜만 교체하고 나머지는 유지(병합)하므로, 짧은 기간(예: 최근 2일)만 담긴 일일 원본을 올려도 과거 데이터가 지워지지 않음. 내용이 같은 달은 건너뜀
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
