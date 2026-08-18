#!/usr/bin/env python3
"""일일브리프 시장 섹션 생성기.

daily_YYYYMMDD.xlsx(FnGuide)와 브리프 초안 HTML을 받아, 초안의 낡은
시장 섹션(시장 한 컷 + 추세 차트)을 기준일 종가로 재생성해 이식한다.

사용 절차 (매일 발행 시):
  1) 아래 CONFIG의 경로·날짜를 갱신
  2) TIPS(6개)·README_TEXTS(7개)를 당일 데이터·뉴스 맥락으로 다시 작성
  3) 실행 후 출력의 '기간 %'를 KOSPI 해설의 {KOSPI_CHG}에 반영
직전 발행본(PUB)에서 표 구조·이름을 추출하므로 PUB는 항상 최신 발행본으로.
"""
import re, datetime, openpyxl

# ---------- CONFIG (매일 갱신) ----------
XLSX = "/root/.claude/uploads/405f6ada-29ad-5785-ac2d-569e3af54ca7/d814737e-daily_20260819.xlsx"
DRAFT = "/root/.claude/uploads/405f6ada-29ad-5785-ac2d-569e3af54ca7/8984af00-20260819.html"
PUB = "archive/2026-08-18.html"      # 구조 추출용 직전 발행본
OUT = "archive/2026-08-19.html"      # 출력
BASE = "2026-08-18"                  # 종가 기준일 (Keys 시트 최근일자)
PUB_DATE = "2026.08.19"              # 발행일 (업데이트 표기)
GRAD = "819"                          # 차트 gradient id suffix (발행일)

UP, DOWN = '#c0392b', '#2a5ca8'
BASE_D = datetime.date.fromisoformat(BASE)
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)

# ---------- Keys 시트: 스냅샷 데이터 ----------
krows = list(wb['Keys'].iter_rows(values_only=True, max_row=110))
def kv(r, cols=(1, 2, 3, 4, 5)):
    return [float(krows[r][c]) for c in cols]

IDX = {'KOSPI': kv(53), 'KOSDAQ': kv(54), 'DOW30': kv(55), 'NASDAQ': kv(56),
       'S&P500': kv(57), 'NIKKEI225': kv(60), 'HANGSENG': kv(61), 'FTSE100': kv(62)}
RATE = {'국고채3년': kv(64), '회사채': kv(65), 'CD91': kv(66), '미국10년': kv(68),
        'SOFR': kv(69), '영국10년': kv(70)}
FX = {'원': kv(72), '엔': kv(73), '위안': kv(74), '파운드': kv(76), '유로': kv(77)}
CMD = {'WTI': kv(80), '두바이': kv(81), '브렌트': kv(82), '금': kv(83), '은': kv(84), '알루미늄': kv(85)}
FUND = {'고객예탁금': kv(87), '신용잔고': kv(88), '미수잔고': kv(89), '수익증권': kv(90)}
FLOW = {'외국인': kv(94, (1, 3, 4, 5)), '개인': kv(95, (1, 3, 4, 5)), '기관': kv(96, (1, 3, 4, 5))}

# ---------- GlobalChart 시트: 월말 시계열 (마지막 13개) ----------
grows = list(wb['GlobalChart'].iter_rows(values_only=True))
def monthly(date_col, val_col, r0, r1):
    # 월별 마지막 관측치로 리샘플. 기준일 이후 날짜(발행일 새벽 행)는 기준일로 귀속
    bym = {}
    for r in range(r0, r1):
        d = grows[r][date_col] if date_col < len(grows[r]) else None
        if isinstance(d, (datetime.datetime, datetime.date)):
            dd = d.date() if isinstance(d, datetime.datetime) else d
            if dd > BASE_D: dd = BASE_D
            v = grows[r][val_col]
            if isinstance(v, (int, float)): bym[(dd.year, dd.month)] = (dd, float(v))
    return [bym[k] for k in sorted(bym)][-13:]

SERIES = {
    'kospi': monthly(64, 65, 15, 76), 'sp500': monthly(64, 66, 15, 76),
    'nikkei': monthly(64, 67, 15, 76), 'us10y': monthly(26, 28, 15, 537),
    'usdkrw': monthly(40, 45, 15, 136), 'wti': monthly(76, 79, 15, 76),
    'gold': monthly(76, 82, 15, 76)}

# 차트 마지막 점을 Keys 시트의 기준일 종가로 통일 (새벽 값 혼입 대비)
_CUR = {'kospi': IDX['KOSPI'][0], 'sp500': IDX['S&P500'][0], 'nikkei': IDX['NIKKEI225'][0],
        'us10y': RATE['미국10년'][0], 'usdkrw': FX['원'][0], 'wti': CMD['WTI'][0], 'gold': CMD['금'][0]}
for _k, _v in _CUR.items():
    _d, _old = SERIES[_k][-1]
    if abs(_old - _v) > 1e-9:
        print(f"[보정] {_k} 마지막 점 {_old} -> {_v} (Keys 기준)")
        SERIES[_k][-1] = (_d, _v)

# ---------- 포맷터 ----------
c2 = lambda v: f"{v:,.2f}"
c0 = lambda v: f"{v:,.0f}"
pct = lambda v: f"{v:+.2f}%"
bp = lambda v: f"{v:+.1f}bp"
cls = lambda v: 'ms-up' if v >= 0 else 'ms-down'
def jo_cur(v): return f"{v/10000:,.2f}조원"
def jo_delta(v): return f"{v/10000:+.2f}조" if abs(v) >= 10000 else f"{v:+,.0f}억"
def flow_fmt(v): return f"{v/1e6:+.2f}조"

# ---------- 스파크라인 ----------
def spark(cur, d1, dw, dm, d3, kind='pct'):
    if kind == 'pct':
        vals = [cur/(1+d3/100), cur/(1+dm/100), cur/(1+dw/100), cur/(1+d1/100), cur]
    else:
        vals = [cur-d3/100, cur-dm/100, cur-dw/100, cur-d1/100, cur]
    lo, hi = min(vals), max(vals)
    ys = [15.0]*5 if hi == lo else [27 - (v-lo)/(hi-lo)*24 for v in vals]
    xs = [3.0, 26.5, 50.0, 73.5, 97.0]
    line = UP if vals[-1] >= vals[0] else DOWN
    dot = UP if d1 >= 0 else DOWN
    pts = ' '.join(f"{x},{y:.1f}" for x, y in zip(xs, ys))
    return (f'<td class="ms-spark"><svg width="100" height="30" viewBox="0 0 100 30" style="display:block;">\n'
            f'<polyline points="{pts}" fill="none" stroke="{line}" stroke-width="1.5" stroke-linejoin="round"/>\n'
            f'<circle cx="97.0" cy="{ys[-1]:.1f}" r="2.5" fill="{dot}"/>\n</svg></td>')

# ---------- 발행본에서 구조 추출 ----------
pub = open(PUB, encoding='utf-8').read()
snap = re.search(r'<div class="market-snapshot">.*?</details>\n</div>', pub, re.S).group(0)
blocks = re.findall(r'<details class="ms-section" open>\n(.*?)\n  </details>', snap, re.S)
summaries = [re.search(r'<summary>.*?</summary>', b, re.S).group(0) for b in blocks]
theads = [re.search(r'<thead>.*?</thead>', b, re.S).group(0) for b in blocks]
NAMES = [re.findall(r'<td class="ms-name">(.*?)</td>', b, re.S) for b in blocks]

# ---------- 스냅샷 행 생성 ----------
def row(name, cur_s, deltas, dfmt, sp=None):
    tds = ''.join(f'<td class="{cls(v)}">{dfmt(v)}</td>' for v in deltas)
    return (f'        <tr><td class="ms-name">{name}</td><td class="ms-price">{cur_s}</td>'
            f'{tds}{sp if sp else ""}</tr>')

order1 = ['KOSPI', 'KOSDAQ', 'S&P500', 'NASDAQ', 'DOW30', 'NIKKEI225', 'HANGSENG', 'FTSE100']
sec1 = [row(nm, c2(IDX[k][0]), IDX[k][1:], pct, spark(*IDX[k])) for nm, k in zip(NAMES[0], order1)]
fx_fmt = {'원': c2, '엔': c2, '위안': lambda v: f"{v:.4f}", '유로': lambda v: f"{v:.4f}", '파운드': lambda v: f"{v:.4f}"}
order2 = ['원', '엔', '위안', '유로', '파운드']
sec2 = [row(nm, fx_fmt[k](FX[k][0]), FX[k][1:], pct, spark(*FX[k])) for nm, k in zip(NAMES[1], order2)]
order3 = ['WTI', '브렌트', '두바이', '금', '은', '알루미늄']
sec3 = [row(nm, c2(CMD[k][0]), CMD[k][1:], pct, spark(*CMD[k])) for nm, k in zip(NAMES[2], order3)]
order4 = ['국고채3년', '회사채', '미국10년', '영국10년', 'CD91', 'SOFR']
sec4 = [row(nm, f"{RATE[k][0]:.3f}", RATE[k][1:], bp, spark(*RATE[k], kind='bp')) for nm, k in zip(NAMES[3], order4)]
order5 = ['고객예탁금', '신용잔고', '미수잔고', '수익증권']
sec5 = [row(nm, jo_cur(FUND[k][0]), FUND[k][1:], jo_delta) for nm, k in zip(NAMES[4], order5)]
sec6 = []
for nm, k in zip(NAMES[5], ['외국인', '개인', '기관']):
    tds = ''.join(f'<td class="{cls(v)}">{flow_fmt(v)}</td>' for v in FLOW[k])
    sec6.append(f'        <tr><td class="ms-name">{nm}</td>{tds}</tr>')

# ---------- 팁 6개 (매일 재작성) ----------
TIPS = [
 '💡 <strong>코스피 6,870 — 전일 -1.55%, 사흘 급등 뒤 조정</strong>입니다. 미국 장기금리 불안에 장중 변동성이 컸고, <strong>코스닥은 834로 -3.52% 급락</strong>했습니다. 다만 1주 기준 +8.26%로 상승분은 지켰습니다. <strong>닛케이 -2.54%, 나스닥 -1.33%</strong>로 글로벌 동반 조정입니다.',
 '💡 <strong>원/달러 1,417.5원(-0.07%)</strong> — 보합권입니다(1개월 -4.87% 원화 강세 기조). <strong>엔화는 159.64엔</strong>입니다.',
 '💡 <strong>금 4,417.80달러(+0.85%) — 사상 최고 재경신</strong>(1개월 +10.10%). 유가도 반등 — WTI 84.50달러(+2.55%), <strong>브렌트유 90.87달러로 90달러 돌파</strong>, 두바이유 87.85달러. 은은 64.99달러 수준입니다.',
 '💡 <strong>미국 10년물 4.731%(+0.7bp)</strong> — 4.7%대에 올라섰고 30년물은 19년 만의 최고 수준입니다. <strong>국고채 3년 3.847%(+5.1bp), 회사채 4.542%(+5.0bp)</strong>로 국내 금리도 동반 상승해 부담이 재부각됐습니다.',
 '💡 <strong>고객예탁금 100.71조(+6,419억) — 이틀째 100조대</strong>입니다(8/14 집계). 신용잔고는 30.43조(-534억)로 숨 고르기, 수익증권은 +4.88조 증가입니다.',
 '💡 <strong>외국인 +0.13조 — 나흘째 순매수</strong>(1주 누적 +7.75조). <strong>개인이 +1.13조로 매수 전환</strong>했고, 기관은 -1.21조입니다.',
]

snap_html = ['<div class="market-snapshot">',
 '  <div class="ms-header">',
 f'    <h2>📊 시장 한 컷 <span class="ms-date">{BASE[:4]}.{BASE[5:7]}.{BASE[8:]} 종가 기준</span></h2>',
 '    <p class="ms-sub">전일·1주·1개월·3개월 변동률을 한눈에. 빨강은 상승, 파랑은 하락입니다.</p>',
 '    <div class="ms-source">',
 '      <span class="ms-source-label">출처</span>',
 '      <span class="ms-source-name">에프앤가이드 <span class="ms-source-en">(FnGuide)</span></span>',
 '      <span class="ms-source-divider">·</span>',
 f'      <span class="ms-source-time">📅 업데이트 {PUB_DATE} 07:30</span>',
 '    </div>',
 '  </div>']
for summ, thead, rows_html, tip in zip(summaries, theads, [sec1, sec2, sec3, sec4, sec5, sec6], TIPS):
    snap_html += ['  <details class="ms-section" open>', f'    {summ}',
                  '    <div class="ms-table-wrap"><table class="ms-table">', f'      {thead}<tbody>']
    snap_html += rows_html
    snap_html += ['      </tbody></table></div>', f'    <div class="ms-tip">{tip}</div>', '  </details>']
snap_html.append('</div>')
SNAP = '\n'.join(snap_html)

# ---------- 차트 ----------
def nice_bounds(vmin, vmax):
    import math
    for exp in range(-3, 7):
        for m in (1, 2, 2.5, 5):
            step = m * 10**exp
            lo = (vmin // step) * step
            hi = math.ceil(vmax / step) * step
            if 2 <= round((hi - lo) / step) <= 4:
                return lo, hi, step
    rng = (vmax - vmin) or 1
    return vmin - rng*0.1, vmax + rng*0.1, rng/3

def chart(key, title, cur_fmt, box_fmt, axis_fmt, tip_fmt, readme):
    data = SERIES[key]
    vals = [v for _, v in data]
    cur = vals[-1]
    color = UP if cur >= vals[0] else DOWN
    lo, hi, step = nice_bounds(min(vals), max(vals))
    y = lambda v: 212 - (v - lo) / (hi - lo) * 182
    xs = [52 + 410*i/12 for i in range(len(vals))]
    p = [f'<svg viewBox="0 0 480 240" class="pro-chart" preserveAspectRatio="xMidYMid meet" role="img">',
         f'  <defs><linearGradient id="grad_{key}_{GRAD}" x1="0" x2="0" y1="0" y2="1">',
         f'    <stop offset="0%" stop-color="{color}" stop-opacity="0.28"/>',
         f'    <stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>',
         f'  </linearGradient></defs>']
    g = lo
    while g <= hi + step/1e6:
        p.append(f'  <line x1="52" y1="{y(g):.1f}" x2="462" y2="{y(g):.1f}" class="pc-grid"/>')
        p.append(f'  <text x="46" y="{y(g)+3:.1f}" class="pc-axis" text-anchor="end">{axis_fmt(g)}</text>')
        g += step
    pts = ' '.join(f"{x:.1f},{y(v):.1f}" for x, v in zip(xs, vals))
    p.append(f'  <polygon points="{pts} 462.0,212.0 52.0,212.0" fill="url(#grad_{key}_{GRAD})"/>')
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    for x, v in zip(xs[:-1], vals[:-1]):
        p.append(f'  <circle cx="{x:.1f}" cy="{y(v):.1f}" r="2.5" fill="{color}"/>')
    p.append(f'  <circle cx="462.0" cy="{y(cur):.1f}" r="5" fill="{color}" stroke="white" stroke-width="2.5"/>')
    by = y(cur) - 25
    p.append(f'  <rect x="408" y="{by:.1f}" width="54" height="18" rx="3" fill="{color}"/>')
    p.append(f'  <text x="435.0" y="{by+12.5:.1f}" class="pc-last-value-box" text-anchor="middle">{box_fmt(cur)}</text>')
    w = 410/12
    for i, ((d, v), x) in enumerate(zip(data, xs)):
        ds = BASE if i == len(data)-1 else d.strftime('%Y-%m-%d')
        p.append(f'  <rect x="{x-w/2:.1f}" y="30" width="{w:.1f}" height="182" fill="transparent" class="pc-hover-zone" data-tooltip="{ds} | {tip_fmt(v)}"/>')
    for i, ((d, v), x) in enumerate(zip(data, xs)):
        lab = f"'{d.strftime('%y')}.1" if d.month == 1 else f"{d.month}월"
        klass = 'pc-xlabel pc-xlabel-last' if i == len(data)-1 else 'pc-xlabel'
        p.append(f'  <text x="{x:.1f}" y="228.0" class="{klass}" text-anchor="middle">{lab}</text>')
    p.append('  <line x1="52" y1="212.0" x2="462" y2="212.0" class="pc-axis-line"/>')
    chg = (cur/vals[0] - 1) * 100
    p.append(f'  <text x="52" y="20" class="pc-period-change" fill="{UP if chg >= 0 else DOWN}">기간 {chg:+.1f}%</text>')
    p.append('</svg>')
    return (f'  <div class="dcv2-card">\n    <div class="dcv2-title-row">\n'
            f'      <div class="dcv2-title">{title} <span class="dcv2-current">{cur_fmt(cur)}</span></div>\n'
            f'      <div class="dcv2-meta">최근 13개월 · 월말 종가</div>\n    </div>\n'
            f'    <div class="dcv2-chart-wrap">\n' + '\n'.join(p) + '\n    </div>\n'
            f'    <div class="dcv2-readme">{readme}</div>\n  </div>')

pt2 = lambda v: c2(v)+'pt'; pt0 = lambda v: c0(v)+'pt'

# ---------- 차트 해설 7개 (매일 재작성) ----------
CHARTS = [
 chart('kospi', '🇰🇷 KOSPI', pt2, pt0, pt0, pt0,
   '📖 KOSPI가 8월 18일 6,870pt로 전일 -1.55%, 사흘 급등 뒤 조정받았습니다. 미국 장기금리 불안에 장중 변동성이 컸지만 1주 기준 +8.26%로 상승분은 지켰습니다. 차트 기간(13개월) 누적은 {KOSPI_CHG}입니다.'),
 chart('sp500', '🇺🇸 S&P500', pt2, pt0, pt0, pt0,
   '📖 미국 S&P500은 8월 18일 7,694pt로 전일 -0.66% 하락했습니다. 나스닥 -1.33%로 기술주 중심 약세입니다.'),
 chart('nikkei', '🇯🇵 NIKKEI 225', pt0, pt0, pt0, pt0,
   '📖 일본 닛케이는 67,461pt로 전일 -2.54% 하락, 사상 최고권에서 되밀렸습니다(1주 +0.73%).'),
 chart('us10y', '🇺🇸 미국 국채 10년 금리', lambda v: f"{v:.3f}%", lambda v: f"{v:.2f}%", lambda v: f"{v:.2f}%", lambda v: f"{v:.2f}%",
   '📖 미국 10년물 금리는 4.731%(+0.7bp)로 4.7%대에 올라섰고, 30년물은 19년 만의 최고 수준입니다. 한국 국고채 3년도 3.847%(+5.1bp)로 동반 상승했습니다.'),
 chart('usdkrw', '💱 원/달러 환율', lambda v: c0(v)+'원', lambda v: c0(v)+'원', lambda v: c0(v)+'원', lambda v: c0(v)+'원',
   '📖 원/달러 환율은 1,417.5원(-0.07%)으로 보합권입니다. 1개월 기준 -4.87%로 원화 강세 기조가 이어지고 있습니다.'),
 chart('wti', '🛢️ WTI 원유', lambda v: f"${v:,.2f}", lambda v: f"${v:,.0f}", lambda v: f"{v:,.2f}$", lambda v: f"${v:,.2f}",
   '📖 WTI 원유는 배럴당 $84.50으로 +2.55% 반등했습니다. 브렌트유는 $90.87로 90달러를 넘어섰고, 두바이유 $87.85. 1개월 기준 +2.44%입니다.'),
 chart('gold', '🥇 금 (스팟)', lambda v: f"${v:,.2f}", lambda v: f"${v:,.0f}", lambda v: f"{v:,.0f}$", lambda v: f"${v:,.0f}",
   '📖 금은 온스당 $4,417.80으로 +0.85% 올라 사상 최고를 재경신했습니다(1개월 +10.10%). 은은 $64.99 수준입니다.'),
]

CHART_SEC = ('<!-- 정교한 차트 섹션 -->\n<div class="detail-charts-v2">\n'
 '  <div class="dcv2-header">\n    <h2>📈 핵심 지표 추세 차트</h2>\n'
 '    <p class="dcv2-sub">실제 가격 흐름을 라인 차트로 확인하세요. 점에 마우스를 올리거나 터치하면 정확한 값이 표시됩니다.</p>\n'
 '    <div class="ms-source">\n      <span class="ms-source-label">출처</span>\n'
 '      <span class="ms-source-name">에프앤가이드 <span class="ms-source-en">(FnGuide)</span></span>\n'
 '      <span class="ms-source-divider">·</span>\n'
 f'      <span class="ms-source-time">📅 업데이트 {PUB_DATE} 07:30</span>\n    </div>\n  </div>\n'
 + '\n'.join(CHARTS) + '\n</div>')

# ---------- 초안에 이식 ----------
draft = open(DRAFT, encoding='utf-8').read()
i0 = draft.index('<div class="market-snapshot">')
i1 = draft.index('<div class="detail-charts-v2">')
depth, j = 0, i1
while True:
    op, cl = draft.find('<div', j+1), draft.find('</div>', j+1)
    if op != -1 and op < cl:
        depth += 1; j = op
    else:
        if depth == 0:
            i_end = cl + 6; break
        depth -= 1; j = cl
open(OUT, 'w', encoding='utf-8').write(draft[:i0] + SNAP + '\n\n\n\n' + CHART_SEC + draft[i_end:])

for k, s in SERIES.items():
    print(k, f"{len(s)}pts", s[0][0].strftime('%y%m'), '→', s[-1][0].strftime('%y%m%d'),
          f"cur={s[-1][1]:,.2f} 기간{(s[-1][1]/s[0][1]-1)*100:+.1f}%")
print("생성 완료:", OUT)
