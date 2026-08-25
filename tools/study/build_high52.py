#!/usr/bin/env python3
"""수정주가 DB -> 52주 신고가 돌파 분석 데이터 (study/high52/data.json)

목적: 최근 1년간 52주 신고가를 돌파한 사례를 모아, 돌파 후 며칠째가
단기고점이었는지 분포를 구해 익절 시점 최적화에 참고할 수 있게 한다.
돌파 당시의 RS 등급·컨센서스(목표주가) 추세를 함께 기록해, 조건별
(예: RS 80 이상 + 컨센서스 20영업일 대비 상향) 성과를 비교한다.

정의
- 돌파일: 종가가 직전 252거래일(약 52주) 종가 최고가를 넘어선 날.
  같은 종목의 연속 돌파는 하나의 흐름이므로, 직전 20거래일 내 돌파가
  없었던 '신선한 돌파'만 사건으로 집계한다.
- 단기고점: 돌파일 이후 종가 기준, 고점 대비 -10% 하락(종가)이 처음
  나오기 전까지의 최고 종가 지점. 추적 구간은 돌파 후 60거래일.
  - confirmed : -10% 되돌림이 나와 고점이 확정된 사례
  - nopullback: 60거래일 동안 -10% 되돌림 없이 상승 지속(고점 = 구간 최고)
  - ongoing   : 데이터가 끝나 아직 판정 불가(최근 돌파)
- RS: 돌파일의 오닐식 RS 등급(db/market/rs, 1~99). 산출 전 시기는 null.
- 컨센서스 추세: 돌파일 목표주가 평균 vs 20거래일 전 목표주가 평균의
  변화율(db/market/consensus). 커버리지가 없으면 null.
- 모집단: 일반 종목만. ETF(db/etf 코드 + 운용사 브랜드명), ETN(코드 5·7
  대역 및 이름), 스팩, 우선주(코드 끝자리 != 0), 돌파일 종가 500원 미만
  종목은 제외.

세그먼트(집계 비교군)
- all    : 전체 돌파
- rs80   : 돌파일 RS >= 80
- cons_up: 컨센서스 20거래일 대비 상향(+)
- strat  : RS >= 80 이고 컨센서스 상향 — '내 전략'

트레일링 스탑 시뮬레이션 (종가 기준, 돌파일 종가 매수)
- 초기 손절: 매수가 대비 -8% 이하 종가 -> 매도
- +10% 도달 후: 매도선을 본전(0%)으로 올림 (이븐스탑)
- +20% 도달 후: 매도선 +10%, +30% 도달 후: +20% ... (10%p 래칫)
- 종가가 매도선 이하로 내려온 날 그 종가에 청산. 시간 제한 없이 매도선에
  걸릴 때까지 보유하며, 데이터 끝까지 미청산이면 open(보유 중).
- 손절(-8%)·이븐스탑 청산을 제외한 '생존' 사례(래칫 익절 + 보유 중)의
  고점(최대 상승폭)이 어느 구간에서 형성되는지 분포를 구한다.

포트폴리오 백테스트 (study/high52/data.json 의 portfolio)
- 1년 전 100만원 시작, '내 전략'(RS 80+ & 컨센↑) 돌파 종목을 돌파일
  종가에 매수. 매수 금액은 당일 포트 평가액의 10% (현금 한도 내).
- 슬롯 10개. 꽉 찬 상태에서 새 후보가 나오면 평가수익률이 가장 낮은
  보유 종목을 당일 종가에 매도하고 교체(당일 매수분은 교체 대상 제외).
- 매도는 위 트레일링 스탑 규칙과 동일. 같은 종목 중복 보유 없음.
- 수수료·세금·호가·부분체결 미반영, 수량은 소수점 허용(금액 기준).

실행: python3 tools/study/build_high52.py   (build_market.py 갱신 후)
출력: study/high52/data.json
"""
import os, glob, json, re, datetime
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
ETF = os.path.join(REPO, 'db', 'etf', '*.parquet')
RS = os.path.join(REPO, 'db', 'market', 'rs', '*.parquet')
CONS = os.path.join(REPO, 'db', 'market', 'consensus', '*.parquet')
OUT = os.path.join(REPO, 'study', 'high52', 'data.json')

LOOKBACK = 252     # 52주(거래일)
COOLDOWN = 20      # 신선한 돌파 판정: 직전 20거래일 내 돌파 없음
FWD = 60           # 돌파 후 추적 거래일 수
PULLBACK = 0.10    # 단기고점 확정 기준 되돌림(고점 종가 대비 -10%)
MIN_PRICE = 500    # 동전주 제외
RS_MIN = 80        # '내 전략' RS 하한
INIT_CASH = 1_000_000   # 백테스트 시작 자금
MAX_POS = 10            # 포트 슬롯 수 (종목당 10%)
CONS_DAYS = 20     # 컨센서스 비교 시점(거래일)
SIM_STOP = 0.08    # 초기 손절폭(-8%)
SIM_STEP = 0.10    # 래칫 간격: +10%마다 매도선을 10%p 아래로 따라 올림


def load_concat(pattern, columns=None):
    frames = [pd.read_parquet(f, columns=columns) for f in sorted(glob.glob(pattern))]
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


def pct(x, q):
    s = sorted(x)
    if not s:
        return None
    k = (len(s) - 1) * q
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def ladder_stop(peak):
    """구간 내 최고 수익률 -> 현재 매도선. +10% 미도달이면 -8%,
    이후 최고 도달 10% 구간보다 10%p 아래(+10%->본전, +20%->+10% ...)"""
    if peak < SIM_STEP - 1e-9:
        return -SIM_STOP
    return SIM_STEP * (int((peak + 1e-9) / SIM_STEP) - 1)


def sim_one(rets):
    """일별 수익률 배열(데이터 끝까지) -> 래칫 트레일링 스탑 청산 결과.

    반환: (outcome, exit_ret, exit_day, peak, peak_day)
    outcome: stop8 / even / trail / open(미청산·보유 중)
    """
    peak, peak_day = 0.0, 0
    for d, r in enumerate(rets, start=1):
        if r > peak:
            peak, peak_day = r, d
        stop = ladder_stop(peak)
        if r <= stop + 1e-9:
            outcome = 'stop8' if stop < -1e-9 else ('even' if stop < 1e-9 else 'trail')
            return outcome, r, d, peak, peak_day
    last = rets[-1] if rets else 0.0
    return 'open', last, len(rets), peak, peak_day


def simulate(events):
    """세그먼트 사건 목록 -> 트레일링 스탑 시뮬레이션 집계 (시간 제한 없음)"""
    runs = [sim_one(e['fwd_all']) for e in events]
    if not runs:
        return None
    done = runs
    closed = [r for r in done if r[0] != 'open']
    exits = [r[1] for r in closed]
    if not exits:
        return None

    outcomes = {}
    for key in ('stop8', 'even', 'trail', 'open'):
        sub = [r for r in done if r[0] == key]
        outcomes[key] = {
            'n': len(sub),
            'share': round(len(sub) / len(done), 4),
            'avg_exit': round(sum(r[1] for r in sub) / len(sub), 4) if sub else None,
            'avg_day': round(sum(r[2] for r in sub) / len(sub), 1) if sub else None,
        }

    # 생존자 = 손절(-8%)·이븐스탑 청산 제외 (래칫 익절 + 보유 중)
    surv = [r for r in done if r[0] in ('trail', 'open')]
    peaks = [r[3] for r in surv]
    peak_days = [r[4] for r in surv]
    buckets = [(0.0, 0.10, '10% 미만'), (0.10, 0.20, '10~20%'), (0.20, 0.30, '20~30%'),
               (0.30, 0.50, '30~50%'), (0.50, 1.00, '50~100%'), (1.00, 99.0, '100% 이상')]
    peak_hist = [{'label': lb, 'lo': lo, 'hi': hi,
                  'count': sum(1 for p in peaks if lo - 1e-9 <= p < hi - 1e-9)}
                 for lo, hi, lb in buckets]

    return {
        'n': len(done),
        'closed': len(closed),
        'mean_exit': round(sum(exits) / len(exits), 4),
        'median_exit': round(pct(exits, 0.5), 4),
        'win': round(sum(1 for x in exits if x > 1e-9) / len(exits), 4),
        'outcomes': outcomes,
        'survivors': {
            'n': len(surv),
            'share': round(len(surv) / len(done), 4),
            'mean_exit': round(sum(r[1] for r in surv) / len(surv), 4) if surv else None,
            'peak_median': round(pct(peaks, 0.5), 4) if peaks else None,
            'peak_p75': round(pct(peaks, 0.75), 4) if peaks else None,
            'peak_day_median': pct(peak_days, 0.5) if peak_days else None,
            'peak_hist': peak_hist,
        },
    }


def backtest(events, px, cal, start_date):
    """'내 전략' 사건으로 포트폴리오 백테스트.

    1년 전 INIT_CASH 시작, 돌파일 종가에 포트 평가액의 10% 매수(현금 한도 내).
    슬롯 MAX_POS개, 꽉 차면 평가수익률 최저 종목을 당일 종가에 매도 후 교체
    (당일 매수분은 교체 대상에서 제외). 매도는 래칫 트레일링 스탑과 동일.
    """
    by_date = {}
    for e in sorted(events, key=lambda x: -(x['rs'] or 0)):
        by_date.setdefault(e['date'], []).append(e)

    cash, positions, trades, curve = float(INIT_CASH), {}, [], []
    for d in [c for c in cal if c >= start_date]:
        ds = d.strftime('%Y-%m-%d')
        # 1) 보유 종목 평가 갱신 + 트레일링 스탑 청산
        for code in list(positions):
            p = positions[code]
            c = px[code].get(d)
            if c is None:                      # 거래 없음(정지 등): 직전가 유지
                continue
            p['last'] = c
            ret = c / p['buy_px'] - 1
            p['peak'] = max(p['peak'], ret)
            stop = ladder_stop(p['peak'])
            if ret <= stop + 1e-9:
                cash += p['qty'] * c
                reason = 'stop8' if stop < -1e-9 else ('even' if stop < 1e-9 else 'trail')
                trades.append({'name': p['name'], 'code': code, 'in': p['in'],
                               'out': ds, 'ret': round(ret, 4), 'reason': reason})
                del positions[code]
        # 2) 신규 후보 매수 (RS 높은 순)
        for e in by_date.get(ds, []):
            if e['code'] in positions:
                continue
            value = cash + sum(p['qty'] * p['last'] for p in positions.values())
            if len(positions) >= MAX_POS:
                # 교체: 당일 매수분 제외, 평가수익률 최저 종목 매도
                cands = [(k, p) for k, p in positions.items() if p['in'] != ds]
                if not cands:
                    continue
                wk, wp = min(cands, key=lambda kv: kv[1]['last'] / kv[1]['buy_px'])
                cash += wp['qty'] * wp['last']
                trades.append({'name': wp['name'], 'code': wk, 'in': wp['in'], 'out': ds,
                               'ret': round(wp['last'] / wp['buy_px'] - 1, 4), 'reason': 'replaced'})
                del positions[wk]
            amt = min(0.10 * value, cash)
            if amt < 1000:
                continue
            c0 = px[e['code']].get(d, e['close'])
            positions[e['code']] = {'qty': amt / c0, 'buy_px': c0, 'last': c0,
                                    'peak': 0.0, 'in': ds, 'name': e['name']}
            cash -= amt
        # 3) 일별 평가액
        value = cash + sum(p['qty'] * p['last'] for p in positions.values())
        curve.append({'d': ds, 'v': round(value)})

    final = curve[-1]['v'] if curve else INIT_CASH
    peak_v, mdd = 0, 0.0
    for c in curve:
        peak_v = max(peak_v, c['v'])
        mdd = min(mdd, c['v'] / peak_v - 1)
    wins = [t['ret'] for t in trades if t['ret'] > 1e-9]
    losses = [t['ret'] for t in trades if t['ret'] <= 1e-9]
    return {
        'initial': INIT_CASH, 'final': final,
        'ret': round(final / INIT_CASH - 1, 4), 'mdd': round(mdd, 4),
        'start': curve[0]['d'] if curve else None, 'end': curve[-1]['d'] if curve else None,
        'n_trades': len(trades),
        'win': round(len(wins) / len(trades), 4) if trades else None,
        'avg_win': round(sum(wins) / len(wins), 4) if wins else None,
        'avg_loss': round(sum(losses) / len(losses), 4) if losses else None,
        'curve': curve,
        'trades': sorted(trades, key=lambda t: t['out'], reverse=True),
        'open': sorted([{'name': p['name'], 'code': k, 'in': p['in'],
                         'ret': round(p['last'] / p['buy_px'] - 1, 4)}
                        for k, p in positions.items()], key=lambda x: -x['ret']),
    }


def aggregate(events):
    """사건 목록 -> {summary, curve, hist, cum} (rets 필드 필요)"""
    settled = [e for e in events if e['status'] != 'ongoing']
    peak_days = [e['peak_day'] for e in settled]
    peak_gains = [e['peak_gain'] for e in settled]

    # 보유기간별 수익률 곡선 (돌파일 종가 매수 가정)
    curve = []
    for d in range(1, FWD + 1):
        rs = [e['rets'][d - 1] for e in events if len(e['rets']) >= d]
        if len(rs) < 20:
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

    return {
        'sim': simulate(events),
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
        'curve': curve, 'hist': hist, 'cum': cum,
    }


def build():
    df = universe_filter(load_concat(PRICE))
    df = df.sort_values(['code', 'date'], kind='mergesort').reset_index(drop=True)
    last_date = df['date'].max()
    cal = list(pd.DatetimeIndex(df['date'].unique()).sort_values())  # 전체 거래일 캘린더
    cal_idx = {d: i for i, d in enumerate(cal)}

    g = df.groupby('code')['close']
    prior_max = g.transform(lambda s: s.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).max())
    df['breakout'] = df['close'] > prior_max
    prev = df.groupby('code')['breakout'].transform(
        lambda s: s.shift(1).rolling(COOLDOWN, min_periods=1).sum())
    df['fresh'] = df['breakout'] & (prev.fillna(0) == 0)

    one_year_ago = last_date - pd.DateOffset(years=1)
    events_idx = df.index[df['fresh'] & (df['date'] >= one_year_ago) & (df['close'] >= MIN_PRICE)]

    # RS 등급 · 컨센서스 조회 테이블
    rs_df = load_concat(RS, columns=['date', 'code', 'rs'])
    rs_map = {(d, c): int(v) for d, c, v in zip(rs_df['date'], rs_df['code'], rs_df['rs'])}
    cons_df = load_concat(CONS, columns=['date', 'code', 'target_price'])
    cons_map = {(d, c): v for d, c, v in
                zip(cons_df['date'], cons_df['code'], cons_df['target_price'])}

    def cons_change(date, code):
        """돌파일 목표주가 vs CONS_DAYS 거래일 전 목표주가 변화율 (없으면 None)"""
        i = cal_idx.get(date)
        if i is None or i < CONS_DAYS:
            return None
        now = cons_map.get((date, code))
        ago = cons_map.get((cal[i - CONS_DAYS], code))
        if now is None or ago is None or not ago:
            return None
        return round(now / ago - 1, 4)

    # 종목별 (날짜, 종가) 배열 준비
    series = {}
    for code, sub in df.groupby('code'):
        series[code] = (sub['close'].tolist(),
                        {d: i for i, d in enumerate(sub['date'].tolist())})

    events = []
    for i in events_idx:
        row = df.loc[i]
        closes, pos = series[row['code']]
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

        events.append({
            'date': row['date'].strftime('%Y-%m-%d'),
            'code': row['code'],
            'name': row['name'],
            'close': base,
            'peak_day': peak_i,                       # 0 = 돌파일이 곧 고점
            'peak_gain': round(peak_v / base - 1, 4),
            'status': status,
            'rs': rs_map.get((row['date'], row['code'])),
            'cons': cons_change(row['date'], row['code']),
            'rets': [round(c / base - 1, 4) for c in fwd],  # 돌파 후 1..FWD일 수익률(곡선용)
            'fwd_all': [c / base - 1 for c in closes[p0 + 1:]],  # 데이터 끝까지(시뮬레이션용)
        })

    # ---- 세그먼트별 집계 ----
    segments = {}
    seg_defs = [
        ('all', '전체', lambda e: True),
        ('rs80', f'RS {RS_MIN}+', lambda e: e['rs'] is not None and e['rs'] >= RS_MIN),
        ('cons_up', '컨센↑', lambda e: e['cons'] is not None and e['cons'] > 0),
        ('strat', f'RS {RS_MIN}+ & 컨센↑',
         lambda e: e['rs'] is not None and e['rs'] >= RS_MIN
         and e['cons'] is not None and e['cons'] > 0),
    ]
    for key, label, cond in seg_defs:
        sub = [e for e in events if cond(e)]
        segments[key] = {'label': label, **aggregate(sub)}

    # ---- 포트폴리오 백테스트 ('내 전략') ----
    strat_events = [e for e in events if seg_defs[3][2](e)]
    codes = {e['code'] for e in strat_events}
    px = {code: dict(zip(sub['date'], sub['close']))
          for code, sub in df[df['code'].isin(codes)].groupby('code')}
    portfolio = backtest(strat_events, px, cal, one_year_ago)

    # 월별 돌파 건수 (전체/전략)
    monthly = {}
    for e in events:
        m = monthly.setdefault(e['date'][:7], {'count': 0, 'strat': 0})
        m['count'] += 1
        if seg_defs[3][2](e):
            m['strat'] += 1

    out = {
        'generated': datetime.date.today().isoformat(),
        'data_start': df['date'].min().strftime('%Y-%m-%d'),
        'data_end': last_date.strftime('%Y-%m-%d'),
        'rs_start': rs_df['date'].min().strftime('%Y-%m-%d'),
        'cons_start': cons_df['date'].min().strftime('%Y-%m-%d'),
        'params': {'lookback': LOOKBACK, 'cooldown': COOLDOWN, 'fwd': FWD,
                   'pullback': PULLBACK, 'min_price': MIN_PRICE,
                   'rs_min': RS_MIN, 'cons_days': CONS_DAYS,
                   'sim_stop': SIM_STOP, 'sim_step': SIM_STEP,
                   'init_cash': INIT_CASH, 'max_pos': MAX_POS},
        'segments': segments,
        'portfolio': portfolio,
        'monthly': [{'month': m, **v} for m, v in sorted(monthly.items())],
        # 사례 테이블용(용량 절약을 위해 rets 제외)
        'events': [{k: e[k] for k in ('date', 'code', 'name', 'close', 'peak_day',
                                      'peak_gain', 'status', 'rs', 'cons')}
                   for e in sorted(events, key=lambda x: x['date'], reverse=True)],
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(OUT) / 1024
    print(f"OK: 사건 {len(events)}건 → {OUT} ({kb:.0f}KB)")
    for key, seg in segments.items():
        s = seg['summary']
        pd_med = s['peak_day_median']
        pg_med = s['peak_gain_median']
        print(f"  [{seg['label']}] {s['events_total']}건 · 고점 중앙값 "
              f"{pd_med if pd_med is not None else '-'}일 · 고점수익률 중앙값 "
              f"{pg_med * 100:+.1f}%" if pg_med is not None else f"  [{seg['label']}] {s['events_total']}건")


if __name__ == '__main__':
    build()
