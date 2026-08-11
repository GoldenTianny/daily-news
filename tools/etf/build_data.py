#!/usr/bin/env python3
# ETF_Raw_YYYYMMDD.xlsx -> 분석용 DB(db/etf/YYYY-MM-DD.parquet) + dates.json 갱신
# raw 파일(가공 전 원본, Sheet1 = ETP Components) 그대로 사용. xlsm/가공본과 구조 동일.
# 검색기 웹은 db/etf/*.parquet를 hyparquet로 직접 읽음 (날짜별 JSON은 2026-08-11 폐지)
# 사용법: python3 build_data.py ~/Downloads/ETF_Raw_20260708.xlsx 2026-07-08 data
import sys, os, json, numbers
import openpyxl

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_DIR = os.path.join(REPO, 'db', 'etf')


def build(xlsm_path, date_key, out_dir):
    wb = openpyxl.load_workbook(xlsm_path, read_only=True, data_only=True)
    ws = wb['Sheet1']
    rows = list(ws.iter_rows(values_only=True))
    ncol = max(len(r) for r in rows)
    nblocks = (ncol + 4) // 5

    def cell(r, c):
        row = rows[r]
        return row[c] if c < len(row) else None

    db_rows = []     # (date, etf_code, etf_name, stock_name, weight)
    n_etf = 0
    comp_names = set()
    for b in range(nblocks):
        base = b * 5
        etf_code = cell(7, base)
        etf_name = cell(8, base)
        if not etf_code or not etf_name:
            continue
        etf_code = str(etf_code).strip()
        etf_name = str(etf_name).strip()

        holds = []          # (comp_name, amount, weight_pct_col)
        total_amt = 0.0
        for r in range(10, len(rows)):
            comp = cell(r, base + 1)
            if comp is None or str(comp).strip() == '':
                continue
            comp = str(comp).strip()
            amt = cell(r, base + 3)
            wpct = cell(r, base + 4)
            amt = float(amt) if isinstance(amt, numbers.Number) else None
            wpct = float(wpct) if isinstance(wpct, numbers.Number) else None
            if amt:
                total_amt += amt
            holds.append((comp, amt, wpct))

        if not holds:
            continue
        n_etf += 1

        for comp, amt, wpct in holds:
            # 비중: 금액 기준 우선, 없으면 엑셀 비중(%) 열, 그것도 없으면 null
            if total_amt > 0 and amt is not None:
                w = round(amt / total_amt * 100, 3)
            elif wpct is not None:
                w = round(wpct, 3)
            else:
                w = None
            db_rows.append((date_key, etf_code, etf_name, comp, w))
            comp_names.add(comp)

    # Parquet 저장 (SNAPPY — 검색기 웹의 hyparquet가 읽는 코덱)
    import duckdb
    import pandas as pd
    os.makedirs(DB_DIR, exist_ok=True)
    dst = os.path.join(DB_DIR, date_key + '.parquet')
    df = pd.DataFrame(db_rows, columns=['date', 'etf_code', 'etf_name', 'stock_name', 'weight'])
    con = duckdb.connect()
    con.execute(f"""
        COPY (SELECT CAST(date AS DATE) AS date, etf_code, etf_name, stock_name,
                     CAST(weight AS DOUBLE) AS weight FROM df)
        TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")

    # dates.json 갱신 (기존 날짜 + 새 날짜, 오름차순) — 검색기의 날짜 목록 인덱스
    os.makedirs(out_dir, exist_ok=True)
    dates_path = os.path.join(out_dir, 'dates.json')
    dates = []
    if os.path.exists(dates_path):
        try:
            dates = json.load(open(dates_path, encoding='utf-8'))
        except Exception:
            dates = []
    if date_key not in dates:
        dates.append(date_key)
    dates = sorted(set(dates))
    json.dump(dates, open(dates_path, 'w', encoding='utf-8'), ensure_ascii=False)

    size_kb = os.path.getsize(dst) / 1024
    print(f"OK  ETF {n_etf}개 | 종목 {len(comp_names)}개 | {len(db_rows):,}행 -> {os.path.relpath(dst, REPO)} ({size_kb:,.0f} KB)")
    print(f"    dates.json -> {dates}")


if __name__ == '__main__':
    xlsm = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Downloads/ETF_Raw_20260708.xlsx')
    date_key = sys.argv[2] if len(sys.argv) > 2 else '2026-07-08'
    out_dir = sys.argv[3] if len(sys.argv) > 3 else 'data'
    build(xlsm, date_key, out_dir)
