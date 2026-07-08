#!/usr/bin/env python3
# ETF최신_YYYYMMDD.xlsm -> 검색기용 JSON (etfs / holdings 만 저장, 나머지는 브라우저가 생성)
# 사용법: python3 build_data.py ~/Downloads/ETF최신_20260708.xlsm 2026-07-08 data
import sys, os, json, numbers
import openpyxl

def build(xlsm_path, date_key, out_dir):
    wb = openpyxl.load_workbook(xlsm_path, read_only=True, data_only=True)
    ws = wb['Sheet1']
    rows = list(ws.iter_rows(values_only=True))
    ncol = max(len(r) for r in rows)
    nblocks = (ncol + 4) // 5

    def cell(r, c):
        row = rows[r]
        return row[c] if c < len(row) else None

    ETFS = {}        # etfCode -> etfName
    HOLDINGS = {}    # etfCode -> [[구성종목명, weight], ...]

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

        hlist = []
        for comp, amt, wpct in holds:
            # 비중: 금액 기준 우선, 없으면 엑셀 비중(%) 열, 그것도 없으면 null
            if total_amt > 0 and amt is not None:
                w = round(amt / total_amt * 100, 3)
            elif wpct is not None:
                w = round(wpct, 3)
            else:
                w = None
            hlist.append([comp, w])
            comp_names.add(comp)
        ETFS[etf_code] = etf_name
        HOLDINGS[etf_code] = hlist

    # data(종목→ETF)와 names는 브라우저가 holdings에서 생성 → 파일에 저장 안 함(용량 절감)
    obj = {"date": date_key, "etfs": ETFS, "holdings": HOLDINGS}

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, date_key + '.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))

    # dates.json 갱신 (기존 날짜 + 새 날짜, 오름차순)
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

    size_mb = os.path.getsize(out_path) / 1e6
    print(f"OK  ETF {n_etf}개 | 종목 {len(comp_names)}개 | {out_path} ({size_mb:.2f} MB)")
    print(f"    dates.json -> {dates}")

if __name__ == '__main__':
    xlsm = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Downloads/ETF최신_20260708.xlsm')
    date_key = sys.argv[2] if len(sys.argv) > 2 else '2026-07-08'
    out_dir = sys.argv[3] if len(sys.argv) > 3 else 'data'
    build(xlsm, date_key, out_dir)
