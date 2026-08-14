#!/usr/bin/env python3
# ETF_price_concensus_YYYYMMDD.xlsx -> 시장 데이터 DB(db/market/) 적재
#   - '수정주가' 시트  -> db/market/price/YYYY-MM.parquet     (date, code, name, close)
#   - 'consencus' 시트 -> db/market/consensus/YYYY-MM.parquet (date, code, name, target_price)
# 월별 파일로 저장하며, 내용이 기존과 같은 달은 건너뛰어 git 변경을 최소화.
# ('ETF raw' 시트는 tools/etf/build_data.py 담당이므로 여기서 다루지 않음)
# 사용법: python3 tools/market/build_market.py <xlsx>
import sys, os, numbers, datetime
import openpyxl
import duckdb
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(REPO, 'db', 'market')

SHEETS = [
    # (시트명, 하위 디렉터리, 값 컬럼명)
    ('수정주가', 'price', 'close'),
    ('consencus', 'consensus', 'target_price'),
]


def parse_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    s = str(v).strip()[:10]
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def extract(ws, value_col):
    """와이드 시계열 시트 -> [(date, code, name, value)] (값 없는 셀은 제외)"""
    rows = list(ws.iter_rows(values_only=True))
    header = {str(r[0]).strip(): i for i, r in enumerate(rows[:14]) if r and r[0]}
    code_row = rows[header['Code']]
    name_row = rows[header['Name']]

    cols = []  # (col_idx, code, name)
    for c in range(1, len(code_row)):
        code = code_row[c]
        if code is None or str(code).strip() == '':
            continue
        name = name_row[c] if c < len(name_row) else None
        cols.append((c, str(code).strip(), str(name).strip() if name else ''))

    out = []
    for r in rows[header['D A T E'] + 1:]:
        d = parse_date(r[0]) if r and r[0] is not None else None
        if d is None:
            continue
        for c, code, name in cols:
            v = r[c] if c < len(r) else None
            if isinstance(v, numbers.Number):
                out.append((d, code, name, float(v)))
    return out


def write_monthly(records, sub, value_col):
    out_dir = os.path.join(DB, sub)
    os.makedirs(out_dir, exist_ok=True)
    df = pd.DataFrame(records, columns=['date', 'code', 'name', value_col])
    n_new = n_same = 0
    for ym, g in df.groupby(df['date'].map(lambda d: f'{d.year:04d}-{d.month:02d}')):
        g = g.sort_values(['date', 'code']).reset_index(drop=True)
        dst = os.path.join(out_dir, ym + '.parquet')
        if os.path.exists(dst):
            old = pd.read_parquet(dst)
            old['date'] = pd.to_datetime(old['date']).dt.date
            if old.reset_index(drop=True).equals(g):
                n_same += 1
                continue
        con = duckdb.connect()
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name,
                         CAST({value_col} AS DOUBLE) AS {value_col} FROM g)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        n_new += 1
    return len(df), df['code'].nunique(), n_new, n_same


def build(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    for sheet, sub, value_col in SHEETS:
        if sheet not in wb.sheetnames:
            print(f"SKIP {sheet}: 시트 없음")
            continue
        records = extract(wb[sheet], value_col)
        n_rows, n_codes, n_new, n_same = write_monthly(records, sub, value_col)
        print(f"OK  {sheet} -> db/market/{sub}/: {n_rows:,}행, 종목 {n_codes:,}개 | "
              f"월 파일 {n_new}개 갱신, {n_same}개 동일(건너뜀)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("사용법: python3 tools/market/build_market.py <ETF_price_concensus_YYYYMMDD.xlsx>")
    build(sys.argv[1])
