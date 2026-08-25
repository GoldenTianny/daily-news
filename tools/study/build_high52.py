#!/usr/bin/env python3
"""수정주가 DB -> 52주 신고가 돌파 분석 데이터 (study/high52/data.json)

목적: 최근 1년간 52주 신고가를 돌파한 사례를 모아, 돌파 후 며칠째가
단기고점이었는지 분포를 구해 익절 시점 최적화에 참고할 수 있게 한다.

정의
- 돌파일: 종가가 직전 252거래일(약 52주) 종가 최고가를 넘어선 날.
  같은 종목의 연속 돌파는 하나의 흐름이므로, 직전 20거래일 내 돌파가
  없었던 '신선한 돌파'만 사건으로 집계한다.
- 단기고점: 돌파일 이후 종가 기준, 고점 대비 -10% 하락(종가)이 처음
  나오기 전까지의 최고 종가 지점. 추적 구간은 돌파 후 60거래일.
  - confirmed : -10% 되돌림이 나와 고점이 확정된 사례
  - nopullback: 60거래일 동안 -10% 되돌림 없이 상승 지속(고점 = 구간 최고)
  - ongoing   : 데이터가 끝나 아직 판정 불가(최근 돌파)
- 모집단: 일반 종목만. ETF(db/etf 코드 + 운용사 브랜드명), ETN(코드 5·7
  대역 및 이름), 스팩, 우선주(코드 끝자리 != 0), 돌파일 종가 500원 미만
  종목은 제외.

실행: python3 tools/study/build_high52.py   (build_market.py 갱신 후)
출력: study/high52/data.json
"""
import os, glob, json, re, datetime
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
ETF = os.path.join(REPO, 'db', 'etf', '*.parquet')
OUT = os.path.join(REPO, 'study', 'high52', 'data.json')

LOOKBACK = 252     # 52주(거래일)
COOLDOWN = 20      # 신선한 돌파 판정: 직전 20거래일 내 돌파 없음
FWD = 60           # 돌파 후 추적 거래일 수
PULLBACK = 0.10    # 단기고점 확정 기준 되돌림(고점 종가 대비 -10%)
MIN_PRICE = 500    # 동전주 제외


def load_prices():
    frames = [pd.read_parquet(f) for f in sorted(glob.glob(PRICE))]
    df = pd.concat(frames, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'])
    return df


def universe_filter(df):
    # db/etf에 등장하는 ETF 코드 + 운용사 브랜드(이름 첫 단어) 수집
    etf_codes, brands = set(), set()
    for f in sorted(glob.glob(ETF)):
        e = pd.read_parquet(f, columns=['etf_code', 'etf_name'])
        etf_codes |= set(e['etf_code'].unique())
        brands |= {n.split(' ')[0] for n in e['etf_name'].unique() if ' ' in n}
    df = df[~df['code'].isin(etf_codes)]
    # 채권·원자재·합성형 등 보유내역이 없어 db/etf에 빠진 ETF는 브랜드명으로 제외
    brand_re = '^(' + '|'.join(re.escape(b) for b in sorted(brands)) + ') '
    df = df[~df['name'].str.match(brand_re)]
    df = df[~df['code'].str.match(r'A[57]')]                   # ETN(코드 5·7 대역) 제외
    df = df[~df['name'].str.contains(' ETN', regex=False)]
    df = df[df['code'].str.endswith('0')]                      # 우선주 등 제외
    df = df[~df['name'].str.contains(r'스팩|스펙', regex=True)]  # 스팩 제외
    return df


def build():
    df = universe_filter(load_prices())
    df = df.sort_values(['code', 'date'], kind='mergesort').reset_index(drop=True)
    last_date = df['date'].max()

    g = df.groupby('code')['close']
    prior_max = g.transform(lambda s: s.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).max())
    df['breakout'] = df['close'] > prior_max
    prev = df.groupby('code')['breakout'].transform(
        lambda s: s.shift(1).rolling(COOLDOWN, min_periods=1).sum())
    df['fresh'] = df['breakout'] & (prev.fillna(0) == 0)

    one_year_ago = last_date - pd.DateOffset(years=1)
    events_idx = df.index[df['fresh'] & (df['date'] >= one_year_ago) & (df['close'] >= MIN_PRICE)]

    # 종목별 (날짜, 종가) 배열 준비
    series = {}
    for code, sub in df.groupby('code'):
        series[code] = (sub['date'].tolist(), sub['close'].tolist(),
                        {d: i for i, d in enumerate(sub['date'].tolist())})

    events = []
    for i in events_idx:
        row = df.loc[i]
        dates, closes, pos = series[row['code']]
        p0 = pos[row['date']]
        base = closes[p0]
        fwd = closes[p0 + 1: p0 + 1 + FWD]

        peak_i, peak_v, status = 0, base, None
        for j, c in enumerate(fwd, start=1):
            if c > peak_v:
                peak_v, peak_i = c, j
            elif c <= peak_v * (1 - PULLBACK):
                status = 'confirmed'
                break
        if status is None:
            status = 'nopullback' if len(fwd) >= FWD else 'ongoing'

        rets = [round(c / base - 1, 4) for c in fwd]
        events.append({
            'date': row['date'].strftime('%Y-%m-%d'),
            'code': row['code'],
            'name': row['name'],
            'close': base,
            'peak_day': peak_i,                       # 0 = 돌파일이 곧 고점
            'peak_gain': round(peak_v / base - 1, 4),
            'status': status,
            'rets': rets,                             # 돌파 후 1..N일 수익률
        })

    # ---- 집계 ----
    def pct(x, q):
        s = sorted(x)
        if not s:
            return None
        k = (len(s) - 1) * q
        f, c = int(k), min(int(k) + 1, len(s) - 1)
        return s[f] + (s[c] - s[f]) * (k - f)

    settled = [e for e in events if e['status'] != 'ongoing']
    peak_days = [e['peak_day'] for e in settled]
    peak_gains = [e['peak_gain'] for e in settled]

    # 보유기간별 수익률 곡선 (돌파일 종가 매수 가정)
    curve = []
    for d in range(1, FWD + 1):
        rs = [e['rets'][d - 1] for e in events if len(e['rets']) >= d]
        if len(rs) < 30:
            break
        curve.append({
            'day': d, 'n': len(rs),
            'mean': round(sum(rs) / len(rs), 4),
            'median': round(pct(rs, 0.5), 4),
            'p25': round(pct(rs, 0.25), 4),
            'p75': round(pct(rs, 0.75), 4),
            'win': round(sum(1 for r in rs if r > 0) / len(rs), 4),
        })

    best_mean = max(curve, key=lambda c: c['mean']) if curve else None
    best_median = max(curve, key=lambda c: c['median']) if curve else None

    # 단기고점 도달일 히스토그램
    buckets = [(0, 0, '돌파일'), (1, 3, '1~3일'), (4, 5, '4~5일'), (6, 10, '6~10일'),
               (11, 15, '11~15일'), (16, 20, '16~20일'), (21, 30, '21~30일'),
               (31, 45, '31~45일'), (46, 60, '46~60일')]
    hist = [{'label': lb, 'lo': lo, 'hi': hi,
             'count': sum(1 for d in peak_days if lo <= d <= hi)}
            for lo, hi, lb in buckets]

    # 누적분포: d일까지 고점이 나온 비율
    cum = [{'day': d, 'p': round(sum(1 for x in peak_days if x <= d) / len(peak_days), 4)}
           for d in [0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 60]] if peak_days else []

    # 월별 돌파 건수
    monthly = {}
    for e in events:
        monthly[e['date'][:7]] = monthly.get(e['date'][:7], 0) + 1

    out = {
        'generated': datetime.date.today().isoformat(),
        'data_start': df['date'].min().strftime('%Y-%m-%d'),
        'data_end': last_date.strftime('%Y-%m-%d'),
        'params': {'lookback': LOOKBACK, 'cooldown': COOLDOWN, 'fwd': FWD,
                   'pullback': PULLBACK, 'min_price': MIN_PRICE},
        'summary': {
            'events_total': len(events),
            'events_settled': len(settled),
            'events_ongoing': len(events) - len(settled),
            'stocks': len({e['code'] for e in events}),
            'peak_day_median': pct(peak_days, 0.5),
            'peak_day_p25': pct(peak_days, 0.25),
            'peak_day_p75': pct(peak_days, 0.75),
            'peak_gain_median': round(pct(peak_gains, 0.5), 4) if peak_gains else None,
            'peak_gain_p75': round(pct(peak_gains, 0.75), 4) if peak_gains else None,
            'best_mean_day': best_mean and best_mean['day'],
            'best_mean_ret': best_mean and best_mean['mean'],
            'best_median_day': best_median and best_median['day'],
            'best_median_ret': best_median and best_median['median'],
        },
        'curve': curve,
        'hist': hist,
        'cum': cum,
        'monthly': [{'month': m, 'count': c} for m, c in sorted(monthly.items())],
        # 사례 테이블용(용량 절약을 위해 rets 제외)
        'events': [{k: e[k] for k in ('date', 'code', 'name', 'close', 'peak_day', 'peak_gain', 'status')}
                   for e in sorted(events, key=lambda x: x['date'], reverse=True)],
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(OUT) / 1024
    print(f"OK: 사건 {len(events)}건(확정 {len(settled)}) → {OUT} ({kb:.0f}KB)")
    if best_median:
        print(f"  중앙값 기준 최적 매도: 돌파 후 {best_median['day']}일 ({best_median['median']:+.2%})")
        print(f"  단기고점 도달일 중앙값: {pct(peak_days, 0.5):.0f}일")


if __name__ == '__main__':
    build()
