#!/usr/bin/env python3
"""거래대금·시가총액 시계열(Peer Analysis 배열) -> db/market/value/ · db/market/mcap/

원본: HTS Peer Analysis 다운로드. 행 = 종목(Code, Name, 결산월), 열 = 일자(Period 행 YYYYMMDD),
값 = 원 단위 금액. 시트명과 무관하게 Code 헤더 행의 항목명으로 DB를 고른다:
  '거래대금' -> db/market/value/ (컬럼 value),  '시가총액' -> db/market/mcap/ (컬럼 mcap),
  '유동시가총액' -> db/market/ffmcap/ (컬럼 ffmcap, 최대주주 등 고정 보유분을 뺀 유통 물량 기준)
'CPD-1TD' 같은 비날짜 열은 제외한다(받은 시각에 따라 가리키는 날짜가 달라 오인 위험).

일일 파일(ETF_price_concensus_*.xlsx)의 스냅샷 시트에 기준일 1일치 '거래대금'·'시가총액'·'유동시가총액' 열(Period 'CPD'/'CPD-n')이
있으면 build_snapshot()으로 같은 DB에 병합한다 (ingest_daily, 열이 없으면 건너뜀).

산출물: db/market/{value,mcap,ffmcap}/YYYY-MM.parquet
  date DATE, code VARCHAR, name VARCHAR('(주)'·'㈜' 접두 제거), value / mcap / ffmcap DOUBLE (원)
- 주식·ETF 모두 포함(원본에 든 코드 그대로). 값이 0 이하이거나 비어 있으면 저장하지 않음
- 원본에 있는 (date, code)만 교체하는 upsert. 내용이 같은 달은 다시 쓰지 않음
- 용도: 유동성 필터, 거래대금 급증 탐지, 시총 규모별 분류, 백테스트 체결 가능 규모 점검 등
    SELECT p.*, v.value FROM 'db/market/price/*.parquet' p
    JOIN 'db/market/value/*.parquet' v USING (date, code)
실행: python3 tools/market/build_value.py <파일.xlsx> [...]   (ingest_daily.py가 시트 구조로 자동 인식)
"""
import sys, os, re, glob, numbers, datetime
import openpyxl
import duckdb
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPECS = {'거래대금': ('value', '거래대금'), '시가총액': ('mcap', '시가총액'), '유동시가총액': ('ffmcap', '유동시가총액')}   # 항목 -> (DB 폴더·컬럼명, 표시명)


def out_dir(col):
    return os.path.join(REPO, 'db', 'market', col)


def cols(col):
    return ['date', 'code', 'name', col]


def clean_name(s):
    return re.sub(r'^\(주\)|^㈜', '', str(s or '').strip()).strip()


def item_sheets(wb):
    """-> [(시트명, 항목)] — Code 헤더 행의 항목명이 SPECS에 있는 시트"""
    out = []
    for ws in wb.worksheets:
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > 16:
                break
            if row and str(row[0] or '').strip() == 'Code':
                item = next((str(v).strip() for v in row[3:8] if str(v or '').strip() in SPECS), None)
                if item:
                    out.append((ws.title, item))
                break
    return out


def is_value_file(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    return bool(item_sheets(wb))


def parse(wb, sn, item):
    col_name = SPECS[item][0]
    rows = list(wb[sn].iter_rows(values_only=True))
    hdr = {str(r[1] or '').strip(): i for i, r in enumerate(rows[:16]) if r and r[1]}
    period = rows[hdr['Period']]
    code_hdr = next(i for i, r in enumerate(rows[:18]) if r and str(r[0] or '').strip() == 'Code')
    item_row = rows[code_hdr]
    date_cols = []
    for c in range(3, len(period)):
        s = str(period[c] or '').strip()
        if re.fullmatch(r'\d{8}', s) and str(item_row[c] or '').strip() == item:
            date_cols.append((c, datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))))
    out = []
    for r in rows[code_hdr + 1:]:
        code = str(r[0] or '').strip()
        if not code.startswith('A'):
            continue
        nm = clean_name(r[1])
        for c, d in date_cols:
            v = r[c] if c < len(r) else None
            if isinstance(v, numbers.Number) and v > 0:
                out.append((d, code, nm, float(v)))
    return pd.DataFrame(out, columns=cols(col_name))


def parse_snapshot(wb, item, date_key):
    """일일 스냅샷 시트의 item 열(Period 'CPD'/'CPD-n') -> 기준일 1일치. 열이 없으면 빈 DataFrame"""
    COLS = cols(SPECS[item][0])
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        hdr = {str(r[1] or '').strip(): i for i, r in enumerate(rows[:16]) if r and r[1]}
        code_hdr = next((i for i, r in enumerate(rows[:18]) if r and str(r[0] or '').strip() == 'Code'), None)
        if code_hdr is None or 'Period' not in hdr:
            continue
        period, item_row = rows[hdr['Period']], rows[code_hdr]
        col = next((c for c in range(3, len(item_row))
                    if str(item_row[c] or '').strip() == item
                    and re.fullmatch(r'CPD(-\d+)?', str(period[c] or '').strip())), None)
        if col is None:
            continue
        d = datetime.date.fromisoformat(date_key)
        out = []
        for r in rows[code_hdr + 1:]:
            code = str(r[0] or '').strip()
            v = r[col] if col < len(r) else None
            if code.startswith('A') and isinstance(v, numbers.Number) and v > 0:
                out.append((d, code, clean_name(r[1]), float(v)))
        return pd.DataFrame(out, columns=COLS)
    return pd.DataFrame(columns=COLS)


def norm(d, col):
    d = d[cols(col)].copy()
    d['date'] = d['date'].astype(str).str[:10]
    d['code'] = d['code'].astype(object)
    d['name'] = d['name'].astype(object)
    d[col] = d[col].astype('float64')
    return d.sort_values(['date', 'code']).reset_index(drop=True)


def write(df, col):
    OUT = out_dir(col)
    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect()
    n_new = n_same = 0
    for ym, g in df.groupby(df['date'].map(lambda d: f'{d.year:04d}-{d.month:02d}')):
        dst = os.path.join(OUT, ym + '.parquet')
        if os.path.exists(dst):
            old = pd.read_parquet(dst)
            old['date'] = pd.to_datetime(old['date']).dt.date
            keys = set(zip(g['date'], g['code']))
            g = pd.concat([old[[k not in keys for k in zip(old['date'], old['code'])]], g])
        g = norm(g, col)
        if os.path.exists(dst) and norm(pd.read_parquet(dst), col).equals(g):
            n_same += 1
            continue
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name, CAST({col} AS DOUBLE) AS {col}
                  FROM g ORDER BY date, code)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        n_new += 1
    size = sum(os.path.getsize(f) for f in glob.glob(os.path.join(OUT, '*.parquet')))
    label = next(v[1] for v in SPECS.values() if v[0] == col)
    print(f"OK  {label} -> db/market/{col}/: {len(df):,}행, 종목 {df['code'].nunique():,}개, "
          f"{df['date'].min()} ~ {df['date'].max()} | 월 파일 {n_new}개 갱신, {n_same}개 동일 "
          f"({size // 1024 // 1024}MB)")
    return n_new


def build(xlsx_path):
    """Peer Analysis 시계열 시트용 (전체 이력). 파일에 든 항목(거래대금·시가총액)을 각각 적재"""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    changed = False
    for sn, item in item_sheets(wb):
        df = parse(wb, sn, item)
        if df.empty:
            print(f'SKIP: {item} 데이터 없음')
            continue
        changed = write(df, SPECS[item][0]) > 0 or changed
    return changed


def build_snapshot(xlsx_path, date_key):
    """일일 파일용: 스냅샷 시트에 거래대금·시가총액 열이 있으면 기준일 1일치 병합"""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    done = False
    for item, (col, label) in SPECS.items():
        df = parse_snapshot(wb, item, date_key)
        if df.empty:
            print(f'SKIP: {label} 열 없음')
            continue
        write(df, col)
        done = True
    return done


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('사용법: python3 tools/market/build_value.py <거래대금·시가총액 시트가 있는 xlsx> [...]')
    for f in sys.argv[1:]:
        build(f)
