#!/usr/bin/env python3
"""터틀 트레이딩 규칙을 KODEX 200(코스피 대용)에 적용한 백테스트 → HTML 리포트.

데이터: db/market/price/*.parquet (종가만 있음 → 아래 근사 사용)
  - 돌파/이탈 판정: 종가 기준 (원래는 장중 고가/저가)
  - N(ATR): 종가 변동폭 |close - prev| 의 20일 와일더 평균
  - 신호는 t일 종가로 판정, 체결은 t+1일 종가 (미래 참조 방지)
  - 롱 온리 (지수 ETF), 수수료+슬리피지 편도 0.05%
규칙:
  S1: 20일 돌파 진입 / 10일 이탈 청산. 직전 20일 돌파가 '수익'이었으면 건너뜀(55일 돌파는 항상 진입)
  S2: 55일 돌파 진입 / 20일 이탈 청산. 필터 없음
  손절 2N (마지막 추가 유닛 기준), 0.5N 상승마다 1유닛 추가, 최대 4유닛, 1유닛 = 자본 1% / N
실행: python3 tools/backtest/turtle_kodex200.py  → tools/backtest/turtle_kodex200.html
"""
import glob, os, math, json, sys, datetime as dt
import pyarrow.parquet as pq

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 대상 ETF: 기본 KODEX 200. 다른 종목은  python3 ... --code A122630 --name "KODEX 레버리지" --out turtle_kodex_lev.html
CODE, NAME, OUT_NAME = 'A069500', 'KODEX 200', 'turtle_kodex200.html'
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == '--code': CODE = args[i + 1]
    if a == '--name': NAME = args[i + 1]
    if a == '--out': OUT_NAME = args[i + 1]
INIT = 10_000_000
FEE = 0.0005          # 편도 (수수료+슬리피지)
RISK = 0.01           # 1유닛 = 자본의 1% / N
MAX_UNITS = 4
OUT = os.path.join(REPO, 'tools', 'backtest', OUT_NAME)

# ---------- 데이터 ----------
rows = []
for f in sorted(glob.glob(os.path.join(REPO, 'db', 'market', 'price', '*.parquet'))):
    for r in pq.read_table(f).to_pylist():
        if r['code'] == CODE and r['close'] and r['close'] > 0:
            rows.append((r['date'], float(r['close'])))
rows.sort()
dates = [d for d, _ in rows]; close = [c for _, c in rows]
n = len(close)

# N (와일더 20일)
N = [None] * n
tr = [0.0] + [abs(close[i] - close[i - 1]) for i in range(1, n)]
for i in range(1, n):
    if i == 20: N[i] = sum(tr[1:21]) / 20
    elif i > 20: N[i] = (19 * N[i - 1] + tr[i]) / 20

def hi(i, k):  # i일 이전 k일 최고 종가 (i 미포함)
    return max(close[i - k:i]) if i >= k else None
def lo(i, k):
    return min(close[i - k:i]) if i >= k else None

# ---------- 시뮬레이션 ----------
def run(entry_k, exit_k, use_filter, label):
    equity = INIT; cash = INIT
    units = []          # [(price, shares)]
    last_add = None; stop = None
    trades = []; eq_curve = []
    pending = None      # 다음날 체결할 주문: ('buy'|'sell', 이유)
    last_bo_won = False # S1 필터용: 직전 20일 돌파(가상 포함) 결과
    hypo = None         # 가상 추적 중인 돌파 [entry_price, stop, exit_k]
    in_pos_days = 0
    for i in range(n):
        p = close[i]
        # ---- 전일 신호 체결 (오늘 종가) ----
        if pending:
            kind, why = pending; pending = None
            if kind == 'buy' and len(units) < MAX_UNITS and N[i]:
                unit_sh = math.floor(equity * RISK / N[i])              # 터틀 규칙상 1유닛
                afford = math.floor(cash / (p * (1 + FEE)))            # 현금 한도 (레버리지 없음)
                shares = min(unit_sh, afford)
                capped = unit_sh > afford
                cost = shares * p * (1 + FEE)
                if shares > 0:
                    cash -= cost; units.append((p, shares)); last_add = p; stop = p - 2 * N[i]
                    trades.append({'d': dates[i].isoformat(), 'act': '매수' if len(units) == 1 else '추가', 'p': p, 'sh': shares,
                                   'why': why + (' · 현금 한도로 축소' if capped else ''), 'units': len(units)})
            elif kind == 'sell' and units:
                sh = sum(s for _, s in units); proceeds = sh * p * (1 - FEE); cash += proceeds
                cost_basis = sum(pp * s for pp, s in units); pnl = proceeds - cost_basis * (1 + FEE)
                trades.append({'d': dates[i].isoformat(), 'act': '청산', 'p': p, 'sh': sh, 'why': why, 'pnl': pnl, 'ret': pnl / (cost_basis * (1 + FEE))})
                units = []; last_add = None; stop = None
        # ---- 자산 평가 ----
        held = sum(s for _, s in units)
        equity = cash + held * p
        if held: in_pos_days += 1
        eq_curve.append(equity)
        if N[i] is None: continue
        # ---- 가상 돌파 추적 (필터용, 20일 돌파만) ----
        if use_filter:
            if hypo:
                if p <= hypo[1]: last_bo_won = False; hypo = None
                elif lo(i, 10) is not None and p < lo(i, 10): last_bo_won = p > hypo[0]; hypo = None
            elif hi(i, 20) is not None and p > hi(i, 20):
                hypo = [p, p - 2 * N[i]]
        # ---- 신호 (오늘 종가 판정 → 내일 체결) ----
        if units:
            if p <= stop: pending = ('sell', '2N 손절')
            elif lo(i, exit_k) is not None and p < lo(i, exit_k): pending = ('sell', f'{exit_k}일 저점 이탈')
            elif len(units) < MAX_UNITS and p >= last_add + 0.5 * N[i]: pending = ('buy', '0.5N 추가')
        else:
            h = hi(i, entry_k)
            if h is not None and p > h:
                skip = use_filter and last_bo_won
                if skip:
                    h55 = hi(i, 55)
                    if h55 is not None and p > h55: pending = ('buy', '55일 돌파(필터 우회)')
                else:
                    pending = ('buy', f'{entry_k}일 돌파')
    # 마지막 평가
    return {'label': label, 'eq': eq_curve, 'trades': trades, 'final': eq_curve[-1], 'exposure': in_pos_days / n}

def stats(eq):
    peak = eq[0]; mdd = 0
    for v in eq:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    years = (dates[-1] - dates[0]).days / 365.25
    ret = eq[-1] / eq[0] - 1
    cagr = (eq[-1] / eq[0]) ** (1 / years) - 1
    return ret, cagr, mdd

S1 = run(20, 10, True, 'S1 · 20일 돌파 / 10일 이탈 (필터)')
S2 = run(55, 20, False, 'S2 · 55일 돌파 / 20일 이탈')
BH = {'label': '단순 보유 (Buy & Hold)', 'eq': [INIT * c / close[0] for c in close], 'trades': [], 'exposure': 1.0}

def trade_stats(tr):
    ex = [t for t in tr if t['act'] == '청산']
    if not ex: return 0, 0, 0, 0
    wins = [t['ret'] for t in ex if t['pnl'] > 0]; loss = [t['ret'] for t in ex if t['pnl'] <= 0]
    return len(ex), len(wins) / len(ex), (sum(wins) / len(wins) if wins else 0), (sum(loss) / len(loss) if loss else 0)

# ---------- 리포트 ----------
def svg_curve(series, w=920, h=300):
    allv = [v for s in series for v in s['eq']]
    lo_, hi_ = min(allv) * 0.98, max(allv) * 1.02
    def X(i): return 50 + (w - 70) * i / (n - 1)
    def Y(v): return 20 + (h - 50) * (1 - (v - lo_) / (hi_ - lo_))
    cols = ['#c62828', '#1565c0', '#9e9e9e']
    out = [f'<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;font:11px sans-serif">']
    for k in range(5):
        v = lo_ + (hi_ - lo_) * k / 4; y = Y(v)
        out.append(f'<line x1="50" x2="{w-20}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/><text x="46" y="{y+4:.1f}" text-anchor="end" fill="#888">{v/1e4:,.0f}만</text>')
    # 연도 눈금
    seen = set()
    for i, d in enumerate(dates):
        key = (d.year, d.month)
        if d.month in (1, 4, 7, 10) and key not in seen:
            seen.add(key); out.append(f'<text x="{X(i):.1f}" y="{h-8}" text-anchor="middle" fill="#888">{d.strftime("%y.%m")}</text>')
    for s, c in zip(series, cols):
        pts = ' '.join(f'{X(i):.1f},{Y(v):.1f}' for i, v in enumerate(s['eq']))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="{1.8 if c!="#9e9e9e" else 1.4}"/>')
    lx = 60
    for s, c in zip(series, cols):
        out.append(f'<rect x="{lx}" y="6" width="14" height="4" fill="{c}"/><text x="{lx+18}" y="11" fill="#444">{s["label"]}</text>')
        lx += 12 + 7 * len(s['label']) + 40
    out.append('</svg>'); return ''.join(out)

def fmt_won(v): return f'{v:,.0f}원'
def pct(v): return f'{v*100:+.1f}%'

rowsh = ''
for s in (S1, S2, BH):
    ret, cagr, mdd = stats(s['eq']); ntr, wr, aw, al = trade_stats(s['trades'])
    rowsh += (f'<tr><td>{s["label"]}</td><td class="n">{fmt_won(s["eq"][-1])}</td><td class="n {"up" if ret>=0 else "dn"}">{pct(ret)}</td>'
              f'<td class="n">{pct(cagr)}</td><td class="n dn">{pct(mdd)}</td><td class="n">{s["exposure"]*100:.0f}%</td>'
              f'<td class="n">{ntr}</td><td class="n">{wr*100:.0f}%</td><td class="n">{pct(aw) if ntr else "–"}</td><td class="n">{pct(al) if ntr else "–"}</td></tr>')

def trade_table(s):
    h = ''
    for t in s['trades']:
        pnl = f'<td class="n {"up" if t["pnl"]>0 else "dn"}">{fmt_won(t["pnl"])} ({pct(t["ret"])})</td>' if t['act'] == '청산' else '<td></td>'
        h += f'<tr><td>{t["d"]}</td><td>{t["act"]}{" ×"+str(t["units"]) if t["act"]!="청산" else ""}</td><td class="n">{t["p"]:,.0f}</td><td class="n">{t["sh"]:,}</td><td>{t["why"]}</td>{pnl}</tr>'
    return h or '<tr><td colspan="6" style="color:#999;text-align:center">거래 없음</td></tr>'

html = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>터틀 백테스트 · {NAME}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;background:#f0f2f5;color:#222;margin:0;font-size:14px;line-height:1.6}}
.hero{{background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:26px 20px}} .hero h1{{margin:0;font-size:22px}} .hero p{{margin:6px 0 0;opacity:.85;font-size:13px}}
.wrap{{max-width:1000px;margin:0 auto;padding:16px}} .card{{background:#fff;border-radius:12px;padding:18px 20px;margin-bottom:14px;box-shadow:0 1px 6px rgba(0,0,0,.06)}}
h2{{font-size:16px;color:#1a237e;margin:0 0 10px}} table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{padding:7px 8px;border-bottom:1px solid #eee;text-align:left;white-space:nowrap}}
th{{background:#fafafa;color:#555;font-size:12px}} td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} .up{{color:#c62828}} .dn{{color:#1565c0}}
.twrap{{overflow-x:auto}} .note{{background:#fff8e1;border-left:3px solid #ffb300;padding:10px 14px;border-radius:6px;font-size:13px;color:#6d4c00}}
ul{{margin:6px 0;padding-left:18px}} li{{margin:2px 0}} details summary{{cursor:pointer;color:#3f51b5;font-weight:600}}
</style></head><body>
<div class="hero"><h1>🐢 터틀 트레이딩 백테스트 · {NAME}</h1><p>{dates[0]} ~ {dates[-1]} · 거래일 {n}일 · 초기자본 {fmt_won(INIT)} · 종가 기준 근사 · 롱 온리</p></div>
<div class="wrap">
<div class="card"><h2>결과 요약</h2><div class="twrap"><table><thead><tr><th>전략</th><th class="n">최종 자산</th><th class="n">총수익률</th><th class="n">연환산</th><th class="n">최대낙폭</th><th class="n">보유비중</th><th class="n">청산 횟수</th><th class="n">승률</th><th class="n">평균 수익</th><th class="n">평균 손실</th></tr></thead><tbody>{rowsh}</tbody></table></div>
<p style="font-size:12.5px;color:#777;margin:8px 0 0">보유비중 = 포지션을 들고 있던 거래일 비율. 평균 수익/손실은 청산 1건당 투입금 대비.</p></div>
<div class="card"><h2>자산 곡선</h2>{svg_curve([S1, S2, BH])}</div>
<div class="card"><h2>규칙 · 가정</h2><ul>
<li><b>S1</b>: 20일 종가 고점 돌파 시 매수, 10일 종가 저점 이탈 시 청산. 직전 20일 돌파(실제 또는 가상)가 수익이었으면 건너뛰되, 55일 돌파면 진입</li>
<li><b>S2</b>: 55일 돌파 매수 / 20일 이탈 청산, 필터 없음</li>
<li>손절 2N (마지막 추가 유닛 가격 기준) · 0.5N 상승마다 1유닛 추가, 최대 4유닛 · 1유닛 = 자본 1% ÷ N (주식수)</li>
<li>레버리지 없음: 1유닛이 보유 현금을 넘으면 현금만큼만 매수. 지수 ETF는 N이 가격의 1% 안팎이라 1유닛이 자본의 대부분을 차지해 추가 매수는 자산이 불어난 뒤에만 가능</li>
<li>N = |종가 − 전일 종가| 의 20일 와일더 평균 (고가·저가가 없어 ATR 대신 사용)</li>
<li>신호는 당일 종가로 판정, 체결은 다음 거래일 종가 · 수수료+슬리피지 편도 {FEE*100:.2f}%</li>
<li>롱 온리. 원래 터틀은 양방향이지만 지수 ETF 매수만 검증</li></ul>
<div class="note">기간이 2년 1개월로 짧고, 이 기간 코스피가 강한 상승장이었습니다. 추세추종 전략은 큰 추세 한두 번이 성적을 좌우하므로 이 결과를 일반화하면 안 됩니다. 종가 기준 판정이라 실제 장중 돌파 매매보다 진입이 하루 늦습니다.</div></div>
<div class="card"><details><summary>S1 거래 내역 ({len([t for t in S1["trades"] if t["act"]=="청산"])}회 청산)</summary><div class="twrap"><table><thead><tr><th>날짜</th><th>행동</th><th class="n">가격</th><th class="n">수량</th><th>사유</th><th class="n">손익</th></tr></thead><tbody>{trade_table(S1)}</tbody></table></div></details></div>
<div class="card"><details><summary>S2 거래 내역 ({len([t for t in S2["trades"] if t["act"]=="청산"])}회 청산)</summary><div class="twrap"><table><thead><tr><th>날짜</th><th>행동</th><th class="n">가격</th><th class="n">수량</th><th>사유</th><th class="n">손익</th></tr></thead><tbody>{trade_table(S2)}</tbody></table></div></details></div>
<p style="font-size:12px;color:#999;text-align:center">생성: {dt.date.today()} · tools/backtest/turtle_kodex200.py ({CODE})</p>
</div></body></html>'''
with open(OUT, 'w', encoding='utf-8') as f: f.write(html)

for s in (S1, S2, BH):
    ret, cagr, mdd = stats(s['eq']); ntr, wr, aw, al = trade_stats(s['trades'])
    print(f"{s['label']:34s} 최종 {s['eq'][-1]:>13,.0f}  수익 {ret*100:+6.1f}%  CAGR {cagr*100:+6.1f}%  MDD {mdd*100:6.1f}%  노출 {s['exposure']*100:3.0f}%  청산 {ntr:2d}  승률 {wr*100:3.0f}%")
print('saved', OUT)
