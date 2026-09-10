#!/usr/bin/env python3
"""터틀 트레이딩 규칙 · 코스피 지수 (OHLC, 1999-12-28~) 백테스트 → HTML 리포트.

데이터: db/market/index/*.parquet (IKS900 코스피, 시가·고가·저가·종가)
규칙 (원형):
  S1: 20일 고가 돌파 진입 / 10일 저가 이탈 청산. 직전 20일 돌파(가상 포함)가 수익이면 건너뛰되 55일 돌파는 진입
  S2: 55일 돌파 진입 / 20일 이탈 청산, 필터 없음
  N = 20일 와일더 ATR(진짜 범위) · 손절 2N(마지막 유닛 기준) · 0.5N 마다 1유닛 추가, 최대 4유닛 · 1유닛 = 자본 1% ÷ N
체결: 돌파·이탈·손절·추가는 스탑 주문처럼 장중 그 수준에서 체결 (시가가 이미 넘어 있으면 시가)
두 가지 계좌:
  현금(롱온리): 지수를 ETF 처럼 매수, 1유닛이 현금을 넘으면 현금만큼. 편도 비용 0.05%
  선물(롱·숏): 유닛 규칙 그대로, 현금 제약 없음(증거금 거래), 양방향. 편도 비용 0.02%
실행: python3 tools/backtest/turtle_kospi.py → tools/backtest/turtle_kospi.html
"""
import glob, os, math, datetime as dt
import pyarrow.parquet as pq

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, 'tools', 'backtest', 'turtle_kospi.html')
INIT = 10_000_000; RISK = 0.01; MAX_UNITS = 4

rows = []
for f in sorted(glob.glob(os.path.join(REPO, 'db', 'market', 'index', '*.parquet'))):
    for r in pq.read_table(f).to_pylist():
        if r['code'] == 'IKS900' and r['close'] and r['close'] > 0:
            rows.append((r['date'], float(r['open'] or r['close']), float(r['high'] or r['close']), float(r['low'] or r['close']), float(r['close'])))
rows.sort()
D = [r[0] for r in rows]; O = [r[1] for r in rows]; H = [r[2] for r in rows]; L = [r[3] for r in rows]; C = [r[4] for r in rows]
n = len(C)

# ATR (와일더 20)
N = [None] * n
tr = [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, n)]
for i in range(1, n):
    if i == 20: N[i] = sum(tr[1:21]) / 20
    elif i > 20: N[i] = (19 * N[i - 1] + tr[i]) / 20

def hh(i, k): return max(H[i - k:i]) if i >= k else None   # i 이전 k일 최고 고가
def ll(i, k): return min(L[i - k:i]) if i >= k else None   # i 이전 k일 최저 저가

def run(entry_k, exit_k, use_filter, label, mode):
    """mode: 'cash' (롱온리·현금제약·ETF 비용) | 'fut' (롱숏·유닛 그대로·선물 비용)"""
    fee = 0.0005 if mode == 'cash' else 0.0002
    cash = INIT; equity = INIT
    pos = 0            # +1 롱 / -1 숏 / 0
    units = []         # [(price, qty)]
    last_add = None; stop = None
    trades = []; eq = []; exposure = 0
    last_bo_won = False; hypo = None   # S1 필터 (롱·숏 각각 가상 추적은 단순화: 방향 무관 최근 돌파)
    def mark(i):
        q = sum(u[1] for u in units)
        if not q: return cash
        avg = sum(p * qq for p, qq in units) / q
        return cash + (C[i] - avg) * q * pos + avg * q * (1 if mode == 'cash' and pos == 1 else 0) - (avg * q if mode == 'cash' and pos == 1 else 0) + (avg * q if mode == 'cash' and pos == 1 else 0)
    # 위 mark 는 복잡하니 명시적으로: 현금 모드는 cash 에서 매수대금이 빠져 있고, 선물 모드는 cash 그대로(증거금 생략) + 미실현손익
    def equity_at(i):
        q = sum(u[1] for u in units)
        if not q: return cash
        avg = sum(p * qq for p, qq in units) / q
        if mode == 'cash': return cash + q * C[i]
        return cash + (C[i] - avg) * q * pos
    def open_unit(i, price, why, direction):
        nonlocal cash, last_add, stop, pos
        if N[i] is None: return
        qty = math.floor(equity * RISK / N[i])
        capped = False
        if mode == 'cash':
            afford = math.floor(cash / (price * (1 + fee)))
            if qty > afford: qty, capped = afford, True
        if qty <= 0: return
        if mode == 'cash': cash -= qty * price * (1 + fee)
        else: cash -= qty * price * fee
        units.append((price, qty)); pos = direction; last_add = price
        stop = price - 2 * N[i] * direction
        trades.append({'d': D[i].isoformat(), 'act': ('매수' if direction == 1 else '매도(숏)') if len(units) == 1 else '추가', 'p': price, 'q': qty,
                       'why': why + (' · 현금 한도로 축소' if capped else ''), 'units': len(units)})
    def close_all(i, price, why):
        nonlocal cash, units, last_add, stop, pos
        q = sum(u[1] for u in units); avg = sum(p * qq for p, qq in units) / q
        if mode == 'cash':
            proceeds = q * price * (1 - fee); cost = q * avg * (1 + fee); cash += proceeds; pnl = proceeds - cost
        else:
            pnl = (price - avg) * q * pos - q * price * fee; cash += pnl; cost = q * avg
        trades.append({'d': D[i].isoformat(), 'act': '청산', 'p': price, 'q': q, 'why': why, 'pnl': pnl, 'ret': pnl / cost, 'dir': pos})
        units = []; last_add = None; stop = None; pos = 0

    for i in range(n):
        if N[i] is None or i < 56:
            eq.append(equity_at(i)); continue
        o, h, l = O[i], H[i], L[i]
        # ---- 보유 중: 손절 → 이탈 → 추가 순서로 장중 체결 ----
        if pos != 0:
            exposure += 1
            if pos == 1:
                if l <= stop: close_all(i, min(stop, o), '2N 손절')
                elif l <= ll(i, exit_k): close_all(i, min(ll(i, exit_k), o), f'{exit_k}일 저가 이탈')
                elif len(units) < MAX_UNITS and h >= last_add + 0.5 * N[i]:
                    open_unit(i, max(last_add + 0.5 * N[i], o), '0.5N 추가', 1)
            else:
                if h >= stop: close_all(i, max(stop, o), '2N 손절')
                elif h >= hh(i, exit_k): close_all(i, max(hh(i, exit_k), o), f'{exit_k}일 고가 돌파')
                elif len(units) < MAX_UNITS and l <= last_add - 0.5 * N[i]:
                    open_unit(i, min(last_add - 0.5 * N[i], o), '0.5N 추가', -1)
        # ---- 미보유: 돌파 진입 (같은 날 청산 후 재진입은 안 함) ----
        if pos == 0 and (not trades or trades[-1]['d'] != D[i].isoformat()):
            up = hh(i, entry_k); dn = ll(i, entry_k)
            skip = use_filter and last_bo_won
            if h > up:
                if skip:
                    if h > hh(i, 55): open_unit(i, max(hh(i, 55), o), '55일 돌파(필터 우회)', 1)
                else: open_unit(i, max(up, o), f'{entry_k}일 고가 돌파', 1)
            elif mode == 'fut' and l < dn:
                if skip:
                    if l < ll(i, 55): open_unit(i, min(ll(i, 55), o), '55일 저가 이탈(필터 우회)', -1)
                else: open_unit(i, min(dn, o), f'{entry_k}일 저가 이탈', -1)
        # ---- S1 필터용 가상 20일 돌파 추적 (롱 기준) ----
        if use_filter:
            if hypo:
                if l <= hypo[1]: last_bo_won = False; hypo = None
                elif l <= ll(i, 10): last_bo_won = min(ll(i, 10), o) > hypo[0]; hypo = None
            elif h > hh(i, 20): hypo = [max(hh(i, 20), o), max(hh(i, 20), o) - 2 * N[i]]
        equity = equity_at(i); eq.append(equity)
    return {'label': label, 'eq': eq, 'trades': trades, 'exposure': exposure / n, 'mode': mode}

CASH_S1 = run(20, 10, True, '현금 · S1 20/10 (필터)', 'cash')
CASH_S2 = run(55, 20, False, '현금 · S2 55/20', 'cash')
FUT_S1 = run(20, 10, True, '선물 롱숏 · S1 20/10 (필터)', 'fut')
FUT_S2 = run(55, 20, False, '선물 롱숏 · S2 55/20', 'fut')
BH = {'label': '단순 보유 (코스피)', 'eq': [INIT * c / C[0] for c in C], 'trades': [], 'exposure': 1.0}
ALL = [CASH_S1, CASH_S2, FUT_S1, FUT_S2, BH]

def stats(eq):
    peak = eq[0]; mdd = 0
    for v in eq: peak = max(peak, v); mdd = min(mdd, v / peak - 1 if peak > 0 else 0)
    yrs = (D[-1] - D[0]).days / 365.25
    return eq[-1] / eq[0] - 1, (eq[-1] / eq[0]) ** (1 / yrs) - 1 if eq[-1] > 0 else -1, mdd
def tstats(tr):
    ex = [t for t in tr if t['act'] == '청산']
    if not ex: return 0, 0, 0, 0, 0
    w = [t['pnl'] for t in ex if t['pnl'] > 0]; lo_ = [t['pnl'] for t in ex if t['pnl'] <= 0]
    pf = (sum(w) / -sum(lo_)) if lo_ and sum(lo_) < 0 else float('inf')
    return len(ex), len(w) / len(ex), (sum(t['ret'] for t in ex if t['pnl'] > 0) / len(w) if w else 0), (sum(t['ret'] for t in ex if t['pnl'] <= 0) / len(lo_) if lo_ else 0), pf

# 연도별 수익률
years = sorted(set(d.year for d in D))
def yearly(eq):
    out = {}
    for y in years:
        idx = [i for i, d in enumerate(D) if d.year == y]
        s = eq[idx[0] - 1] if idx[0] > 0 else eq[idx[0]]; e = eq[idx[-1]]
        out[y] = e / s - 1 if s > 0 else 0
    return out
YR = {s['label']: yearly(s['eq']) for s in ALL}

def fmt_won(v): return f'{v:,.0f}원'
def pct(v): return ('+' if v >= 0 else '') + f'{v*100:.1f}%'

def svg_curve(series, w=960, h=360):
    vals = [max(v, 1) for s in series for v in s['eq']]
    lo_, hi_ = math.log(min(vals)), math.log(max(vals) * 1.05)
    X = lambda i: 60 + (w - 80) * i / (n - 1)
    Y = lambda v: 16 + (h - 46) * (1 - (math.log(max(v, 1)) - lo_) / (hi_ - lo_))
    cols = ['#c62828', '#ef6c00', '#1565c0', '#00897b', '#9e9e9e']
    out = [f'<svg viewBox="0 0 {w} {h}" style="width:100%;font:11px sans-serif">']
    for v in [1e7, 2e7, 5e7, 1e8, 2e8, 5e8, 1e9]:
        if math.log(v) < lo_ or math.log(v) > hi_: continue
        y = Y(v); out.append(f'<line x1="60" x2="{w-20}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/><text x="56" y="{y+4:.1f}" text-anchor="end" fill="#888">{v/1e8:g}억</text>' if v >= 1e8 else f'<line x1="60" x2="{w-20}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/><text x="56" y="{y+4:.1f}" text-anchor="end" fill="#888">{v/1e4:,.0f}만</text>')
    for i, d in enumerate(D):
        if d.year % 2 == 0 and (i == 0 or D[i - 1].year != d.year):
            out.append(f'<text x="{X(i):.1f}" y="{h-8}" text-anchor="middle" fill="#888">{d.year}</text>')
    for s, c in zip(series, cols):
        step = max(1, n // 1500)
        pts = ' '.join(f'{X(i):.1f},{Y(v):.1f}' for i, v in enumerate(s['eq']) if i % step == 0 or i == n - 1)
        out.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="1.6"/>')
    lx = 70
    for s, c in zip(series, cols):
        out.append(f'<rect x="{lx}" y="4" width="14" height="4" fill="{c}"/><text x="{lx+18}" y="9" fill="#444">{s["label"]}</text>'); lx += 14 + 6.2 * len(s['label']) + 34
    out.append('</svg>'); return ''.join(out)

sum_rows = ''
for s in ALL:
    ret, cagr, mdd = stats(s['eq']); ntr, wr, aw, al, pf = tstats(s['trades'])
    sum_rows += (f'<tr><td>{s["label"]}</td><td class="n">{fmt_won(s["eq"][-1])}</td><td class="n {"up" if ret>=0 else "dn"}">{pct(ret)}</td><td class="n">{pct(cagr)}</td>'
                 f'<td class="n dn">{pct(mdd)}</td><td class="n">{s["exposure"]*100:.0f}%</td><td class="n">{ntr}</td><td class="n">{wr*100:.0f}%</td>'
                 f'<td class="n">{pct(aw) if ntr else "–"}</td><td class="n">{pct(al) if ntr else "–"}</td><td class="n">{("%.2f" % pf) if ntr and pf != float("inf") else "–"}</td></tr>')

yr_head = ''.join(f'<th class="n">{s["label"]}</th>' for s in ALL)
yr_rows = ''
for y in years:
    yr_rows += f'<tr><td>{y}</td>' + ''.join(f'<td class="n {"up" if YR[s["label"]][y] >= 0 else "dn"}">{pct(YR[s["label"]][y])}</td>' for s in ALL) + '</tr>'

def trade_table(s):
    h = ''
    for t in s['trades']:
        pnl = f'<td class="n {"up" if t["pnl"]>0 else "dn"}">{fmt_won(t["pnl"])} ({pct(t["ret"])})</td>' if t['act'] == '청산' else '<td></td>'
        h += f'<tr><td>{t["d"]}</td><td>{t["act"]}{" ×"+str(t["units"]) if t["act"]!="청산" else ""}</td><td class="n">{t["p"]:,.2f}</td><td class="n">{t["q"]:,}</td><td>{t["why"]}</td>{pnl}</tr>'
    return h or '<tr><td colspan="6" style="color:#999;text-align:center">거래 없음</td></tr>'
def details(s):
    nex = len([t for t in s['trades'] if t['act'] == '청산'])
    return (f'<div class="card"><details><summary>{s["label"]} 거래 내역 ({nex}회 청산)</summary><div class="twrap"><table><thead><tr><th>날짜</th><th>행동</th><th class="n">지수</th><th class="n">수량</th><th>사유</th><th class="n">손익</th></tr></thead><tbody>{trade_table(s)}</tbody></table></div></details></div>')

html = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>터틀 백테스트 · 코스피 2000~2026</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;background:#f0f2f5;color:#222;margin:0;font-size:14px;line-height:1.6}}
.hero{{background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:26px 20px}} .hero h1{{margin:0;font-size:22px}} .hero p{{margin:6px 0 0;opacity:.85;font-size:13px}}
.wrap{{max-width:1080px;margin:0 auto;padding:16px}} .card{{background:#fff;border-radius:12px;padding:18px 20px;margin-bottom:14px;box-shadow:0 1px 6px rgba(0,0,0,.06)}}
h2{{font-size:16px;color:#1a237e;margin:0 0 10px}} table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{padding:6px 8px;border-bottom:1px solid #eee;text-align:left;white-space:nowrap}}
th{{background:#fafafa;color:#555;font-size:12px}} td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} .up{{color:#c62828}} .dn{{color:#1565c0}}
.twrap{{overflow-x:auto}} .note{{background:#fff8e1;border-left:3px solid #ffb300;padding:10px 14px;border-radius:6px;font-size:13px;color:#6d4c00}}
ul{{margin:6px 0;padding-left:18px}} li{{margin:2px 0}} details summary{{cursor:pointer;color:#3f51b5;font-weight:600}}
</style></head><body>
<div class="hero"><h1>🐢 터틀 트레이딩 백테스트 · 코스피 지수</h1><p>{D[0]} ~ {D[-1]} · 거래일 {n:,}일 ({(D[-1]-D[0]).days/365.25:.1f}년) · 초기자본 {fmt_won(INIT)} · 시가·고가·저가·종가 사용 · 진짜 ATR</p></div>
<div class="wrap">
<div class="card"><h2>결과 요약</h2><div class="twrap"><table><thead><tr><th>전략</th><th class="n">최종 자산</th><th class="n">총수익률</th><th class="n">연환산</th><th class="n">최대낙폭</th><th class="n">보유비중</th><th class="n">청산</th><th class="n">승률</th><th class="n">평균 수익</th><th class="n">평균 손실</th><th class="n">손익비(PF)</th></tr></thead><tbody>{sum_rows}</tbody></table></div>
<p style="font-size:12.5px;color:#777;margin:8px 0 0">손익비(PF) = 총이익 ÷ 총손실. 평균 수익/손실은 청산 1건당 투입금 대비. 지수 1포인트 = 1원으로 계산.</p></div>
<div class="card"><h2>자산 곡선 (로그 눈금)</h2>{svg_curve(ALL)}</div>
<div class="card"><h2>연도별 수익률</h2><div class="twrap"><table><thead><tr><th>연도</th>{yr_head}</tr></thead><tbody>{yr_rows}</tbody></table></div></div>
<div class="card"><h2>규칙 · 가정</h2><ul>
<li><b>S1</b>: 20일 고가 돌파 진입 / 10일 저가 이탈 청산. 직전 20일 돌파(가상 포함)가 수익이었으면 건너뛰되 55일 돌파면 진입 · <b>S2</b>: 55일 돌파 / 20일 이탈, 필터 없음</li>
<li>N = 20일 와일더 ATR(진짜 범위) · 손절 2N (마지막 유닛 기준) · 0.5N 마다 1유닛 추가, 최대 4유닛 · 1유닛 = 자본 1% ÷ N</li>
<li>돌파·이탈·손절·추가는 <b>장중 그 수준에서 체결</b> (스탑 주문). 시가가 이미 넘어 있으면 시가 체결. 같은 날 청산 후 재진입은 없음</li>
<li><b>현금 계좌</b>: 롱온리, 지수를 ETF 처럼 매수, 1유닛이 현금을 넘으면 현금만큼 (레버리지 없음), 편도 0.05%</li>
<li><b>선물 계좌</b>: 롱·숏 양방향, 유닛 규칙 그대로(증거금 거래라 현금 제약 없음), 편도 0.02%. 원형 터틀에 가장 가까움</li>
<li>배당·이자·세금 없음. 지수 자체를 거래한다고 가정 (실제 ETF·선물과의 괴리 없음)</li></ul>
<div class="note">26년 8개월에 IT버블 붕괴(2000), 금융위기(2008), 코로나(2020), 2022 약세장, 2025~26 급등이 모두 들어 있어 이전 2년 테스트보다 훨씬 신뢰할 만합니다. 다만 하나의 지수, 하나의 파라미터 세트라 "터틀이 코스피에서 통한다"는 결론이 아니라 "이 규칙이 코스피에서 어떻게 행동했는가"로 읽어야 합니다.</div></div>
{''.join(details(s) for s in ALL[:4])}
<p style="font-size:12px;color:#999;text-align:center">생성: {dt.date.today()} · tools/backtest/turtle_kospi.py</p>
</div></body></html>'''
with open(OUT, 'w', encoding='utf-8') as f: f.write(html)
for s in ALL:
    ret, cagr, mdd = stats(s['eq']); ntr, wr, aw, al, pf = tstats(s['trades'])
    print(f"{s['label']:26s} 최종 {s['eq'][-1]:>14,.0f}  수익 {ret*100:+8.1f}%  CAGR {cagr*100:+6.1f}%  MDD {mdd*100:6.1f}%  노출 {s['exposure']*100:3.0f}%  청산 {ntr:3d}  승률 {wr*100:3.0f}%  PF {pf if pf!=float('inf') else 0:.2f}")
print('saved', OUT)
