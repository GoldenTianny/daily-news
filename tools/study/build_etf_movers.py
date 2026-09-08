#!/usr/bin/env python3
"""ETF 보유내역 DB -> '편입 비중 증가 TOP 10' 이후 수익률 검증 (study/etf-movers/data.json)

목적: ETF 검색기 초기화면의 '편입 비중 증가 TOP 10' 위젯에 오른 종목이
실제로 그 뒤에 시장보다 잘 갔는지 확인한다. 같은 방식으로 뽑은
'편입 비중 감소 TOP 10'을 대조군으로 함께 본다.

위젯 재현 (tools/etf/index.html weightMovers()와 동일)
- 비교 시점: 기준일보다 10개 앞선 스냅샷(파일 기준 '10영업일 전').
  스냅샷이 10개 미만이면 5개·1개 앞 순으로 대체.
- 종목별 Δ = Σ_ETF (오늘 비중 − 비교일 비중). 비교일에 없던 ETF는 건너뛰고,
  ETF가 비교일에 그 종목을 안 담았으면 비교일 비중 0 (신규 편입).
- 레버리지·인버스·곱버스 ETF 제외, 현금·채권·선물 등 비주식 항목 제외.
- Δ > 0.005 인 종목 중 상위 10개 = TOP 10 (Δ < -0.005 하위 10개 = 대조군).

수익률 측정
- 기준일(종가 기준일)의 데이터는 다음 영업일에 업로드돼 위젯에 뜬다.
  따라서 진입 = 기준일 다음 거래일 종가, 청산 = 진입 후 1·5·10·20거래일 종가.
- 비교 기준: KODEX 200 수익률, 위젯 모집단(ETF 보유 종목 중 가격 매칭)
  동일가중 평균, 같은 모집단의 중앙값.
- 직전 모멘텀: 진입일 종가 기준 직전 10거래일 수익률 (비중 증가가
  '이미 오른 종목'을 뽑는 것인지 확인용).
- 종목명이 가격 DB에 없는 항목(해외주식·우선주·리츠 등)은 수익률 집계에서 제외.

실행: python3 tools/study/build_etf_movers.py   (ingest_daily.py 5.5단계)
출력: study/etf-movers/data.json
"""
import os, glob, json, re, datetime, math
import pandas as pd
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ETF_DIR = os.path.join(REPO, 'db', 'etf')
PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
OUT = os.path.join(REPO, 'study', 'etf-movers', 'data.json')

OFFS = (10, 5, 1)          # 위젯과 같은 우선순위
TOPN = 10
HORIZONS = (1, 5, 10, 20)  # 진입 후 거래일
PRIOR = 10                 # 직전 모멘텀 측정 거래일
MIN_DELTA = 0.005
BENCH_CODE = 'A069500'     # KODEX 200

LEV = re.compile(r'레버리지|인버스|곱버스', re.I)
NONEQ = re.compile(r'현금|예금|달러|엔화|유로|위안|스왑|선물|국고|통안|콜론|CD금리|KOFR|SOFR|전단채|채권|사채|만기|T-?Bill', re.I)


def snapshot_dates():
    return sorted(os.path.basename(f)[:-8] for f in glob.glob(os.path.join(ETF_DIR, '*.parquet')))


def load_snapshot(date):
    df = pd.read_parquet(os.path.join(ETF_DIR, date + '.parquet'),
                         columns=['etf_code', 'etf_name', 'stock_name', 'weight'])
    # 웹(hyparquet)과 동일하게 소수 3자리
    df['weight'] = df['weight'].round(3)
    return df


def movers(cur, past):
    """종목별 비중합 변화(%p) Series — 위젯 weightMovers() ② 재현"""
    cur = cur[~cur['etf_name'].str.contains(LEV, na=False)]
    cur = cur[cur['etf_code'].isin(set(past['etf_code'])) & cur['weight'].notna()]
    pw = past.set_index(['etf_code', 'stock_name'])['weight'].fillna(0)
    pw = pw[~pw.index.duplicated()]
    key = pd.MultiIndex.from_arrays([cur['etf_code'].values, cur['stock_name'].values])
    delta = cur['weight'].values - pw.reindex(key).fillna(0).values
    s = pd.Series(delta, index=cur['stock_name'].values).groupby(level=0).sum()
    s = s[[not NONEQ.search(n) for n in s.index]]
    return s.sort_values(ascending=False)


def load_prices(start):
    frames = []
    for f in sorted(glob.glob(PRICE)):
        if os.path.basename(f)[:7] < start[:7]:
            continue
        frames.append(pd.read_parquet(f, columns=['date', 'code', 'name', 'close']))
    px = pd.concat(frames, ignore_index=True)
    px['date'] = px['date'].astype(str)
    wide = px.pivot_table(index='date', columns='name', values='close')
    bench = px[px['code'] == BENCH_CODE].set_index('date')['close']
    return wide, bench


def r(x, nd=4):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), nd)


def build():
    dates = snapshot_dates()
    if len(dates) < 2:
        print('SKIP: ETF 스냅샷이 2개 미만'); return
    # 첫 비교 가능일 이전 달부터 가격 로드 (직전 모멘텀 계산 여유 포함)
    first = dates[0]
    start = (datetime.date.fromisoformat(first) - datetime.timedelta(days=45)).isoformat()
    wide, bench = load_prices(start)
    TD = list(wide.index)
    cache = {}

    def snap(d):
        if d not in cache:
            cache[d] = load_snapshot(d)
        return cache[d]

    def fwd(entry_i, h):
        if entry_i + h >= len(TD):
            return None
        return wide.iloc[entry_i + h] / wide.iloc[entry_i] - 1

    events = []      # 시그널 날짜별 기록
    rows = []        # 종목 단위 (group, h, ret, ...)
    for i, d in enumerate(dates):
        off = next((o for o in OFFS if i - o >= 0), None)
        if off is None:
            continue
        s = movers(snap(d), snap(dates[i - off]))
        later = [t for t in TD if t > d]
        if not later:
            continue
        entry = later[0]
        ei = TD.index(entry)
        top = s[s > MIN_DELTA].head(TOPN)
        bot = s[s < -MIN_DELTA].sort_values().head(TOPN)
        univ = [n for n in s.index if n in wide.columns]
        prior = (wide.iloc[ei] / wide.iloc[ei - PRIOR] - 1) if ei - PRIOR >= 0 else None

        ev = {'sig_date': d, 'comp_date': dates[i - off], 'off': off, 'entry': entry,
              'mkt': {}, 'groups': {}}
        for h in HORIZONS:
            fr = fwd(ei, h)
            if fr is None:
                continue
            u = fr.reindex(univ).dropna()
            k = (bench.get(TD[ei + h], np.nan) / bench.get(entry, np.nan) - 1)
            ev['mkt'][str(h)] = {'kodex': r(k), 'univ': r(u.mean()), 'med': r(u.median())}
        if prior is not None:
            ev['mkt']['prior'] = r(prior.reindex(univ).median())

        for gname, sel in (('top', top), ('bottom', bot)):
            items = []
            for name, dl in sel.items():
                it = {'name': name, 'delta': r(dl, 2), 'ret': {}}
                if name in wide.columns:
                    if prior is not None:
                        it['prior'] = r(prior.get(name))
                    for h in HORIZONS:
                        fr = fwd(ei, h)
                        if fr is None:
                            continue
                        v = fr.get(name)
                        it['ret'][str(h)] = r(v)
                        if v is not None and not np.isnan(v):
                            m = ev['mkt'][str(h)]
                            rows.append({'group': gname, 'h': h, 'sig_date': d, 'name': name,
                                         'ret': v, 'kodex': m['kodex'], 'univ': m['univ'],
                                         'med': m['med']})
                items.append(it)
            ev['groups'][gname] = items
        events.append(ev)

    df = pd.DataFrame(rows)
    summary = []
    port = []
    for gname in ('top', 'bottom'):
        for h in HORIZONS:
            x = df[(df.group == gname) & (df.h == h)]
            if x.empty:
                continue
            summary.append({
                'group': gname, 'h': h, 'n': int(len(x)), 'n_dates': int(x.sig_date.nunique()),
                'mean': r(x.ret.mean()), 'median': r(x.ret.median()),
                'win': r((x.ret > 0).mean()),
                'beat_kodex': r((x.ret > x.kodex).mean()), 'beat_univ': r((x.ret > x.univ).mean()),
                'beat_med': r((x.ret > x.med).mean()),
            })
            # 날짜별 동일가중 포트폴리오
            p = x.groupby('sig_date').agg(ret=('ret', 'mean'), kodex=('kodex', 'first'),
                                          univ=('univ', 'first'), med=('med', 'first'))
            ex_k = p.ret - p.kodex
            ex_u = p.ret - p.univ
            t = None
            if len(p) > 2 and ex_u.std(ddof=1) > 0:
                t = ex_u.mean() / (ex_u.std(ddof=1) / math.sqrt(len(p)))
            port.append({
                'group': gname, 'h': h, 'n_dates': int(len(p)),
                'ret': r(p.ret.mean()), 'kodex': r(p.kodex.mean()), 'univ': r(p.univ.mean()),
                'med': r(p.med.mean()),
                'excess_kodex': r(ex_k.mean()), 'excess_univ': r(ex_u.mean()),
                'beat_kodex_days': r((ex_k > 0).mean()), 'beat_univ_days': r((ex_u > 0).mean()),
                't_univ': r(t, 2),
            })

    # 직전 모멘텀 요약
    prior_sum = {}
    for gname in ('top', 'bottom'):
        vals = [it['prior'] for ev in events for it in ev['groups'][gname] if it.get('prior') is not None]
        prior_sum[gname] = {'n': len(vals), 'mean': r(np.mean(vals)) if vals else None,
                            'median': r(np.median(vals)) if vals else None}
    mk = [ev['mkt']['prior'] for ev in events if ev['mkt'].get('prior') is not None]
    prior_sum['mkt_med'] = r(np.mean(mk)) if mk else None

    # 자주 오른 종목
    freq = {}
    for gname in ('top', 'bottom'):
        c = {}
        for ev in events:
            for it in ev['groups'][gname]:
                a = c.setdefault(it['name'], [0, 0.0])
                a[0] += 1; a[1] += it['delta']
        freq[gname] = [{'name': n, 'n': v[0], 'delta': r(v[1] / v[0], 1)}
                       for n, v in sorted(c.items(), key=lambda kv: -kv[1][0])[:15]]

    out = {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'params': {'off': OFFS[0], 'topn': TOPN, 'horizons': list(HORIZONS), 'prior': PRIOR,
                   'min_delta': MIN_DELTA, 'bench': 'KODEX 200'},
        'range': {'etf_first': dates[0], 'etf_last': dates[-1], 'n_snapshots': len(dates),
                  'n_signals': len(events), 'price_last': TD[-1]},
        'summary': summary, 'port': port, 'prior': prior_sum, 'freq': freq,
        'events': sorted(events, key=lambda e: e['sig_date'], reverse=True),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(OUT) / 1024
    print(f"OK: 시그널 {len(events)}일 ({dates[0]}~{dates[-1]}) → {OUT} ({kb:.0f}KB)")
    for p in port:
        print(f"  [{p['group']:6s} h={p['h']:2d}] 날짜 {p['n_dates']:2d} · 수익 {p['ret']*100:+.2f}% · "
              f"모집단평균 {p['univ']*100:+.2f}% · 초과 {p['excess_univ']*100:+.2f}% · "
              f"이긴날 {p['beat_univ_days']*100:.0f}% · t={p['t_univ']}")


if __name__ == '__main__':
    build()
