# ETF 보유내역 DB (db/etf/)

국내 상장 ETF 전 종목의 일별 보유내역 스냅샷. **날짜별 Parquet 파일 1개**(불변)로 저장됩니다.

- 원천: HTS 다운로드 엑셀 → `tools/etf/data/YYYY-MM-DD.json`(웹 검색기용) → 본 Parquet(분석용)
- 생성: `tools/etf/build_data.py` 실행 시 자동 생성 (단독 재생성은 `python3 tools/etf/build_db.py`)
- 규모: 날짜당 약 67,000행 (ETF 918개 × 보유종목), 파일당 약 380KB
- 압축: SNAPPY — ETF 검색기 웹페이지(hyparquet)가 브라우저에서 직접 읽는 코덱
- 소비처: ① 분석(DuckDB/pandas) ② ETF 검색기 웹(1차 소스, JSON은 폴백)

## 스키마 (롱 포맷)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DATE | 기준일 (파일명과 동일) |
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
- `weight`는 ETF별 원본 데이터 기준이라 합계가 정확히 100이 아닐 수 있습니다
- 과거 데이터 정정 시 해당 날짜 파일을 `--force`로 재생성하면 됩니다 (git 이력에 변경 기록 남음)
