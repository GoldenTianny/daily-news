#!/usr/bin/env python3
"""투자자별 순매수대금 시계열(Peer Analysis 배열, 항목 '<투자자> 순매수대금(일간)') -> db/market/flow/

원본: HTS Peer Analysis 다운로드. 투자자 한 종류당 시트(파일) 하나, 행 = 종목, 열 = 일자(Period YYYYMMDD),
값 = 일간 순매수대금(백만원, 매수-매도). 시트명과 무관하게 Code 헤더 행의 항목명으로 투자자를 판별한다.
'CPD'/'CPD-1TD' 같은 비날짜 열은 제외(받은 시각에 따라 장중 값이거나 가리키는 날짜가 달라짐).

일일 파일(ETF_price_concensus_*.xlsx)의 스냅샷 시트에 같은 항목 열(Period 'CPD'/'CPD-n')이 있으면
build_snapshot()으로 기준일 1일치를 병합한다 (ingest_daily 5단계, 열이 없으면 건너뜀).

산출물: db/market/flow/YYYY-MM.parquet — 투자자별 열을 가진 넓은 표 (단위: 원, 원본 백만원 x 1e6)
  date DATE, code VARCHAR, name VARCHAR, 아래 INVESTORS 열 DOUBLE (미적재 투자자는 NULL)
- 투자자별로 나눠 올려도 되도록 **열 단위 병합**: 원본에 있는 투자자 열만 (date, code) 기준으로 교체하고
  다른 투자자 열은 기존 값을 유지한다. 내용이 같은 달은 다시 쓰지 않음
- 용도: 외국인·기관 수급 추적(연속 순매수, 누적 순매수/시총), 개인 역지표, 수급 동반 돌파 백테스트 등
    SELECT f.date, f.code, f.frgn, f.retail, f.frgn / m.mcap AS 외인순매수_시총비
    FROM 'db/market/flow/*.parquet' f JOIN 'db/market/mcap/*.parquet' m USING (date, code)
실행: python3 tools/market/build_flow.py <파일.xlsx> [...]   (ingest_daily.py가 시트 구조로 자동 인식)
"""
import sys, os, re, glob, numbers, datetime
import openpyxl
import duckdb
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, 'db', 'market', 'flow')
SUFFIX = '순매수대금(일간)'
UNIT = 1e6                       # 원본 단위 백만원 -> 원
# 원본 투자자명 -> 열 이름 (HTS 투자자 구분 순서)
INVESTORS = {
    '개인': 'retail', '외국인총합계': 'frgn', '기관계': 'inst',
    '금융투자': 'fin_inv', '보험': 'insurance', '투신': 'trust', '사모펀드': 'pe',
    '은행': 'bank', '기타금융': 'other_fin', '연기금': 'pension',
    '국가지자체': 'govt', '기타법인': 'corp',
}
VALS = list(INVESTORS.values())
KEYS = ['date', 'code']


def clean_name(s):
    return re.sub(r'^\(주\)|^㈜', '', str(s or '').strip()).strip()


def investor_of(label):
    """'외국인총합계 순매수대금(일간)' -> 'frgn' (모르는 투자자명이면 None)"""
    label = str(label or '').strip()
    if not label.endswith(SUFFIX):
        return None
    return INVESTORS.get(label[:-len(SUFFIX)].strip())


def item_sheets(wb):
    """-> [(시트명, 열 이름)] — Code 헤더 행 항목이 '<투자자> 순매수대금(일간)'인 시트"""
    out = []
    for ws in wb.worksheets:
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > 16:
                break
            if row and str(row[0] or '').strip() == 'Code':
                for v in row[3:8]:
                    if str(v or '').strip().endswith(SUFFIX):
                        col = investor_of(v)
                        if col is None:
                            print(f'   ! {ws.title}: 알 수 없는 투자자 항목 "{v}" — 건너뜀 (INVESTORS에 추가 필요)')
                        else:
                            out.append((ws.title, col))
                        break
                break
    return out


def is_flow_file(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    return any(str(row[0] or '').strip() == 'Code' and any(str(v or '').strip().endswith(SUFFIX) for v in row[3:8])
               for ws in wb.worksheets for i, row in zip(range(17), ws.iter_rows(values_only=True)) if row)


def parse_sheet(ws, col):
    rows = list(ws.iter_rows(values_only=True))
    hdr = {str(r[1] or '').strip(): i for i, r in enumerate(rows[:16]) if r and r[1]}
    period = rows[hdr['Period']]
    code_hdr = next(i for i, r in enumerate(rows[:18]) if r and str(r[0] or '').strip() == 'Code')
    item_row = rows[code_hdr]
    date_cols = []
    for c in range(3, len(period)):
        s = str(period[c] or '').strip()
        if re.fullmatch(r'\d{8}', s) and investor_of(item_row[c]) == col:
            date_cols.append((c, datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))))
    out = []
    for r in rows[code_hdr + 1:]:
        code = str(r[0] or '').strip()
        if not code.startswith('A'):
            continue
        nm = clean_name(r[1])
        for c, d in date_cols:
            v = r[c] if c < len(r) else None
            if isinstance(v, numbers.Number):
                out.append((d, code, nm, float(v) * UNIT))
    return pd.DataFrame(out, columns=KEYS + ['name', col])


def merge_frames(frames):
    """투자자별 DataFrame들을 (date, code) 기준으로 옆으로 합침"""
    df = None
    for g in frames:
        if df is None:
            df = g
        else:
            df = df.merge(g, on=KEYS, how='outer', suffixes=('', '_r'))
            df['name'] = df['name'].fillna(df.pop('name_r'))
    return df


def norm(d):
    d = d[KEYS + ['name'] + VALS].copy()
    d['date'] = d['date'].astype(str).str[:10]
    d['code'] = d['code'].astype(object)
    d['name'] = d['name'].astype(object)
    for v in VALS:
        d[v] = d[v].astype('float64')
    return d.sort_values(KEYS).reset_index(drop=True)


def write(df):
    """df에 있는 투자자 열만 (date, code) 기준으로 교체, 나머지 열은 기존 값 유지"""
    cols = [v for v in VALS if v in df.columns]
    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect()
    n_new = n_same = 0
    for ym, g in df.groupby(df['date'].map(lambda d: f'{d.year:04d}-{d.month:02d}')):
        dst = os.path.join(OUT, ym + '.parquet')
        if os.path.exists(dst):
            old = pd.read_parquet(dst)
            old['date'] = pd.to_datetime(old['date']).dt.date
            m = old.merge(g[KEYS + ['name'] + cols], on=KEYS, how='outer', suffixes=('', '_new'))
            m['name'] = m.pop('name_new').fillna(m['name'])
            for v in cols:
                new = m.pop(v + '_new')
                m[v] = new.where(new.notna(), m[v])
            g = m
        for v in VALS:
            if v not in g.columns:
                g[v] = None
        g = norm(g)
        if os.path.exists(dst) and norm(pd.read_parquet(dst)).equals(g):
            n_same += 1
            continue
        sel = ', '.join(f'CAST({v} AS DOUBLE) AS {v}' for v in VALS)
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name, {sel} FROM g ORDER BY date, code)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        n_new += 1
    size = sum(os.path.getsize(f) for f in glob.glob(os.path.join(OUT, '*.parquet')))
    names = {v: k for k, v in INVESTORS.items()}
    print(f"OK  순매수대금 -> db/market/flow/: {len(df):,}행, 종목 {df['code'].nunique():,}개, "
          f"{df['date'].min()} ~ {df['date'].max()} | 투자자 {', '.join(names[c] for c in cols)} | "
          f"월 파일 {n_new}개 갱신, {n_same}개 동일 ({size // 1024 // 1024}MB)")
    return n_new


def build(xlsx_paths):
    """Peer Analysis 시계열용 (전체 이력). 투자자별 파일 여러 개를 함께 넘기면 한 번에 병합"""
    if isinstance(xlsx_paths, str):
        xlsx_paths = [xlsx_paths]
    frames, seen = [], set()
    for f in xlsx_paths:
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        for sn, col in item_sheets(wb):
            if col in seen:
                print(f'    {os.path.basename(f)} / {sn} · {col}: 중복 투자자 — 건너뜀')
                continue
            g = parse_sheet(wb[sn], col)
            print(f'    {os.path.basename(f)} / {sn} · {col}: {len(g):,}행')
            if not g.empty:
                frames.append(g)
                seen.add(col)
    if not frames:
        print('SKIP: 순매수대금 데이터 없음')
        return False
    return write(merge_frames(frames)) > 0


def parse_snapshot(xlsx_path, date_key):
    """일일 스냅샷 시트의 '<투자자> 순매수대금(일간)' 열(Period 'CPD'/'CPD-n') -> 기준일 1일치"""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    d = datetime.date.fromisoformat(date_key)
    frames = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        hdr = {str(r[1] or '').strip(): i for i, r in enumerate(rows[:16]) if r and r[1]}
        code_hdr = next((i for i, r in enumerate(rows[:18]) if r and str(r[0] or '').strip() == 'Code'), None)
        if code_hdr is None or 'Period' not in hdr:
            continue
        period, item_row = rows[hdr['Period']], rows[code_hdr]
        for c in range(3, len(item_row)):
            col = investor_of(item_row[c])
            if col is None or not re.fullmatch(r'CPD(-\d+)?', str(period[c] or '').strip()):
                continue
            out = [(d, str(r[0]).strip(), clean_name(r[1]), float(r[c]) * UNIT)
                   for r in rows[code_hdr + 1:]
                   if str(r[0] or '').strip().startswith('A') and c < len(r) and isinstance(r[c], numbers.Number)]
            frames.append(pd.DataFrame(out, columns=KEYS + ['name', col]))
    return merge_frames(frames) if frames else None


def build_snapshot(xlsx_path, date_key):
    """일일 파일용: 스냅샷 시트에 순매수대금 열이 있으면 기준일 1일치 병합"""
    df = parse_snapshot(xlsx_path, date_key)
    if df is None or df.empty:
        print('SKIP: 순매수대금 열 없음')
        return False
    write(df)
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('사용법: python3 tools/market/build_flow.py <순매수대금 시트가 있는 xlsx> [...]')
    build(sys.argv[1:])
