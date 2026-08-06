#!/usr/bin/env python3
"""ETF 검색기 JSON(tools/etf/data/*.json) -> 분석용 DB(db/etf/*.parquet) 변환.

- 롱 포맷: date, etf_code, etf_name, stock_name, weight (ETF x 보유종목 1행)
- 날짜별 파일 하나(불변 스냅샷). 이미 존재하는 날짜는 건너뜀 (--force로 재생성)
- 조회 예:
    import duckdb
    duckdb.sql("SELECT * FROM 'db/etf/*.parquet' WHERE stock_name='삼성전자' ORDER BY date, weight DESC")

사용법: python3 tools/etf/build_db.py [--force] [날짜 ...]
        (날짜 생략 시 data/ 폴더의 전체 날짜 처리)
"""
import sys, os, json, glob
import duckdb

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(REPO, 'tools', 'etf', 'data')
DB_DIR = os.path.join(REPO, 'db', 'etf')


def build(date_key, force=False):
    src = os.path.join(DATA_DIR, date_key + '.json')
    dst = os.path.join(DB_DIR, date_key + '.parquet')
    if not os.path.exists(src):
        print(f"SKIP {date_key}: 원본 JSON 없음")
        return False
    if os.path.exists(dst) and not force:
        print(f"SKIP {date_key}: 이미 존재")
        return False

    obj = json.load(open(src, encoding='utf-8'))
    rows = []
    for code, items in obj['holdings'].items():
        name = obj.get('etfs', {}).get(code, code)
        for comp, w in items:
            rows.append((obj['date'], code, name, comp, w))

    os.makedirs(DB_DIR, exist_ok=True)
    import pandas as pd
    df = pd.DataFrame(rows, columns=['date', 'etf_code', 'etf_name', 'stock_name', 'weight'])
    con = duckdb.connect()
    con.execute(f"""
        COPY (SELECT CAST(date AS DATE) AS date, etf_code, etf_name, stock_name,
                     CAST(weight AS DOUBLE) AS weight FROM df)
        TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
    size_kb = os.path.getsize(dst) / 1024
    print(f"OK  {date_key}: {len(rows):,}행 -> {os.path.relpath(dst, REPO)} ({size_kb:,.0f} KB)")
    return True


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--force']
    force = '--force' in sys.argv
    dates = args or sorted(
        os.path.basename(p)[:-5] for p in glob.glob(os.path.join(DATA_DIR, '*.json'))
        if os.path.basename(p) != 'dates.json')
    n = sum(build(d, force) for d in dates)
    print(f"완료: {n}개 날짜 변환")
