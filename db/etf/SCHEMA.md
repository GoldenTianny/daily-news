# ETF 보유내역 DB (db/etf/)

국내 상장 ETF 전 종목의 일별 보유내역 스냅샷. **날짜별 Parquet 파일 1개**(불변)로 저장됩니다.

- 원천: HTS 다운로드 엑셀 → 본 Parquet (`tools/etf/build_data.py`가 직접 생성) — `ETF_Raw_*.xlsx`(Sheet1)와 통합본 `ETF_price_concensus_*.xlsx`('ETF raw' 시트) 모두 지원
- 생성: `python3 tools/etf/build_data.py <원본.xlsx> <YYYY-MM-DD> tools/etf/data` — 재생성 시에도 원본 엑셀 필요
- 규모: 날짜당 약 67,000행 (ETF 918개 × 보유종목), 파일당 약 380KB
- 압축: SNAPPY — ETF 검색기 웹페이지(hyparquet)가 브라우저에서 직접 읽는 코덱
- 소비처: ① 분석(DuckDB/pandas) ② ETF 검색기 웹 — 본 Parquet가 유일한 데이터 소스
  (날짜별 JSON 폴백은 2026-08-11 폐지, `tools/etf/data/`에는 날짜 목록 인덱스 `dates.json`만 유지)

## 스키마 (롱 포맷)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DATE | 종가 기준일 (파일명과 동일) — 원본 엑셀은 이 날짜의 익영업일에 다운로드됨 |
| `etf_code` | VARCHAR | ETF 종목코드 (예: A069500) |
| `etf_name` | VARCHAR | ETF 종목명 |
| `stock_name` | VARCHAR | 보유 종목명 (현금·선물 등 비주식 포함) |
| `weight` | DOUBLE | 보유 비중(%) — 금액 기준, 없으면 원본 비중 열, 둘 다 없으면 NULL |

## 쿼리 예시 (DuckDB — 서버 불필요)

```python
import duckdb

# 특정 종목을 담은 ETF를 비중순으로
duckdb.sql("""
  SELECT etf_name, weight FROM 'db/etf/*.parquet'
  WHERE stock_name = '삼성전자' AND date = '2026-08-07'
  ORDER BY weight DESC
""")

# 종목의 ETF 편입 비중합 시계열 (수급 프록시)
duckdb.sql("""
  SELECT date, SUM(weight) AS total_w, COUNT(*) AS n_etf
  FROM 'db/etf/*.parquet' WHERE stock_name = 'NAVER'
  GROUP BY date ORDER BY date
""")
```

pandas는 `pd.read_parquet('db/etf/2026-08-07.parquet')`로 바로 읽을 수 있습니다.

## 유의

- 결측일: 주말·공휴일 및 미업로드일은 파일이 없습니다 (수집일만 존재)
- 날짜 의미: 2026-08-07 이전 업로드분은 업로드일 기준으로 저장돼 있던 것을 전 영업일(종가 기준일)로 일괄 정정함 (2026-08-08 정비). 이후 업로드분은 파일명에 종가 기준일을 사용
- `weight`는 ETF별 원본 데이터 기준이라 합계가 정확히 100이 아닐 수 있습니다
- 과거 데이터 정정 시 원본 엑셀로 `build_data.py`를 다시 실행하면 해당 날짜 파일이 덮어써집니다 (git 이력에 변경 기록 남음)
