#!/usr/bin/env python3
"""OHLC + 미너비니 템플릿 -> VCP(변동성 수축 패턴) 판정 DB (db/market/vcp/)

마크 미너비니의 VCP는 베이스(조정 구간) 안에서 조정 폭이 단계적으로 줄어드는 모습이다.
고점에서 밀린 폭(수축)이 2~4회에 걸쳐 점점 얕아지고, 마지막 수축의 고점이 매수 기준선(피벗)이 된다.

모집단 (미너비니 템플릿을 1차 필터로 사용)
  - 8개 조건 모두 충족(passed), 또는
  - 조건 ⑤(종가 > 50일선)만 미달 — 베이스 후반에는 주가가 50일선 아래로 잠시 내려가는 일이
    흔해, 이를 빼면 완성 직전 종목을 놓친다. 추세 구조 조건(②③④)은 반드시 충족해야 하므로
    pass_n=7 이면서 ⑤만 빠진 경우로 한정한다.

판정 (기준일 기준 최근 WINDOW 거래일 고가·저가)
  1. 베이스 고점 = 창 안의 최고 고가. 그 뒤로 MIN_BASE 거래일 이상 남아 있어야 베이스로 본다
  2. 베이스 고점 이후를 지그재그(ZIGZAG 반전폭)로 훑어 고점→저점 하락(수축)들을 추출
  3. 수축 2~5회, 첫 수축이 가장 깊고 MAX_FIRST 이하, 현재가가 피벗 대비 -MAX_DIST ~ +MAX_ABOVE
  4. 등급 — 완성(fit): 마지막 수축이 FIT_LAST 이하이고 첫 수축의 FIT_RATIO 이하이며 끝까지 좁아짐
             형성 중(near): 같은 기준의 완화판(NEAR_LAST · NEAR_RATIO). 아직 여유가 있는 단계
  5. 피벗 = 마지막 수축의 고점. 종가가 이를 넘으면 돌파

산출물: db/market/vcp/YYYY-MM.parquet
  date, code, name, close, rs, in_tpl(8개 통과 여부), pivot_px, dist(피벗 대비 %, 음수=아래),
  n_cont(수축 횟수), d1~d4(각 수축 깊이 %), base_days(베이스 길이), tight(마지막 수축 깊이 %),
  tier('fit' 완성 / 'near' 형성 중)
실행: python3 tools/market/build_vcp.py        (미계산 날짜만)
      python3 tools/market/build_vcp.py --all  (전체 재계산)
"""
import sys, os, glob
import duckdb
import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OHLC = os.path.join(REPO, 'db', 'market', 'ohlc', '*.parquet')
PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
MV = os.path.join(REPO, 'db', 'market', 'minervini', '*.parquet')
OUT = os.path.join(REPO, 'db', 'market', 'vcp')

WINDOW = 120      # 베이스를 찾는 창 (거래일)
MIN_BASE = 10     # 베이스 최소 길이 (거래일)
ZIGZAG = 0.05     # 지그재그 반전폭 — 이보다 작은 흔들림은 잡음으로 보고 무시
MAX_FIRST = 0.35  # 첫 수축 최대 깊이 (너무 깊은 베이스 제외)
MIN_CONT, MAX_N = 2, 5    # 수축 횟수 범위
MONO = 1.05       # '완성' 판정 시 허용하는 단조성 이탈 (직전의 이 배까지는 수축으로 인정)
FIT_LAST, FIT_RATIO = 0.12, 0.6     # 완성: 마지막 수축 깊이 · 첫 수축 대비 비율
NEAR_LAST, NEAR_RATIO = 0.20, 0.85  # 형성 중: 같은 기준의 완화판
MAX_DIST = 0.20   # 현재가가 피벗 대비 이보다 더 아래면 제외 (베이스에서 너무 멀다)
MAX_ABOVE = 0.05  # 피벗을 이보다 더 넘어섰으면 제외 (이미 돌파해 매수 시점이 지남)
MAX_CONT = 4      # 저장할 수축 깊이 개수
COND_MA50 = 4     # 조건 ⑤(종가 > 50일선)의 flags 비트 자리 (0-based)


def contractions(high, low):
    """베이스 고점 이후의 수축 목록 -> (깊이 리스트, 피벗, 베이스 길이, 등급).
    등급: 'fit' 완성 / 'near' 형성 중 / None 해당 없음"""
    n = len(high)
    i_peak = int(np.argmax(high))
    if n - i_peak - 1 < MIN_BASE:      # 고점이 너무 최근이면 아직 베이스가 아님
        return None, None, None, None
    h, l = high[i_peak:], low[i_peak:]

    # 지그재그: 베이스 고점에서 시작해 하락(-1)/상승(+1) 방향을 번갈아 확정
    pivots = [('H', float(h[0]))]
    direction, ext = -1, float(l[0])
    for i in range(1, len(h)):
        if direction < 0:                                   # 하락 중 — 저점 갱신 추적
            if l[i] < ext:
                ext = float(l[i])
            elif h[i] >= ext * (1 + ZIGZAG):                # 반등 확인 -> 저점 확정
                pivots.append(('L', ext))
                direction, ext = 1, float(h[i])
        else:                                               # 상승 중 — 고점 갱신 추적
            if h[i] > ext:
                ext = float(h[i])
            elif l[i] <= ext * (1 - ZIGZAG):                # 되밀림 확인 -> 고점 확정
                pivots.append(('H', ext))
                direction, ext = -1, float(l[i])
    pivots.append(('L' if direction < 0 else 'H', ext))      # 진행 중인 마지막 극값

    # 고점 -> 저점 쌍을 수축으로 환산
    depths, pivot_price = [], None
    for a, b in zip(pivots, pivots[1:]):
        if a[0] == 'H' and b[0] == 'L' and a[1] > 0:
            depths.append((a[1] - b[1]) / a[1])
            pivot_price = a[1]
    if not (MIN_CONT <= len(depths) <= MAX_N) or depths[0] > MAX_FIRST:
        return None, None, None, None
    if depths[0] < max(depths) - 1e-9:      # 첫 수축이 가장 깊어야 VCP (중간에 더 깊게 밀리면 실패한 베이스)
        return None, None, None, None
    mono = all(depths[i + 1] <= depths[i] * MONO for i in range(len(depths) - 1))
    if depths[-1] <= FIT_LAST and depths[-1] <= depths[0] * FIT_RATIO and mono:
        tier = 'fit'                      # 수축이 끝까지 좁아진 완성형
    elif depths[-1] <= NEAR_LAST and depths[-1] <= depths[0] * NEAR_RATIO:
        tier = 'near'                     # 좁아지는 중이나 아직 여유가 있음
    else:
        return None, None, None, None
    return depths, pivot_price, n - i_peak - 1, tier


def compute(targets, series):
    """targets: DataFrame(date, code, name, close, rs, in_tpl) / series: code -> (dates, high, low)"""
    out = []
    for code, g in targets.groupby('code', sort=False):
        s = series.get(code)
        if s is None:
            continue
        dates, high, low = s
        pos = {d: i for i, d in enumerate(dates)}
        for r in g.itertuples(index=False):
            i = pos.get(r.date)
            if i is None or i + 1 < MIN_BASE + 5:
                continue
            j = max(0, i + 1 - WINDOW)
            depths, pivot_px, base_days, tier = contractions(high[j:i + 1], low[j:i + 1])
            if depths is None or not pivot_px:
                continue
            dist = r.close / pivot_px - 1
            if dist < -MAX_DIST or dist > MAX_ABOVE:
                continue
            d = list(depths[:MAX_CONT]) + [None] * (MAX_CONT - min(len(depths), MAX_CONT))
            out.append((r.date, code, r.name, r.close, r.rs, r.in_tpl, round(pivot_px, 2),
                        round(dist * 100, 2), len(depths),
                        *[round(x * 100, 2) if x is not None else None for x in d],
                        base_days, round(depths[-1] * 100, 2), tier))
    cols = ['date', 'code', 'name', 'close', 'rs', 'in_tpl', 'pivot_px', 'dist', 'n_cont',
            *[f'd{k}' for k in range(1, MAX_CONT + 1)], 'base_days', 'tight', 'tier']
    return pd.DataFrame(out, columns=cols)


def norm(x):
    x = x.copy()
    x['date'] = x['date'].astype(str).str[:10]
    for c in ('code', 'name', 'tier'):
        x[c] = x[c].astype(object)
    for c in ('close', 'pivot_px', 'dist', 'tight', *[f'd{k}' for k in range(1, MAX_CONT + 1)]):
        x[c] = x[c].astype('float64')
    for c in ('rs', 'n_cont', 'base_days'):
        x[c] = x[c].astype('int64')
    x['in_tpl'] = x['in_tpl'].astype(bool)
    return x.sort_values(['date', 'code']).reset_index(drop=True)


def build(force=False):
    con = duckdb.connect()
    # 조건 충족 종목이 0인 날은 파일에 행이 남지 않으므로, '마지막으로 계산한 날짜' 이후만 새로 계산
    last_done = None
    os.makedirs(OUT, exist_ok=True)
    if not force and glob.glob(os.path.join(OUT, '*.parquet')):
        r = con.execute(f"SELECT max(date) FROM '{os.path.join(OUT, '*.parquet')}'").fetchone()[0]
        last_done = str(r)[:10] if r else None

    targets = con.execute(f"""
        SELECT m.date, m.code, m.name, m.close, coalesce(m.rs, 0) AS rs, m.passed AS in_tpl
        FROM '{MV}' m
        WHERE m.passed OR (m.pass_n = 7 AND (m.flags & {1 << COND_MA50}) = 0)
        ORDER BY m.code, m.date
    """).df()
    targets['date'] = targets['date'].astype(str).str[:10]
    if last_done:
        targets = targets[targets['date'] > last_done]
    if targets.empty:
        print('SKIP: 새로 계산할 날짜 없음')
        return
    # 기준일 종가는 미너비니 DB 값(가격 DB와 동일), 고가·저가는 OHLC DB
    px = con.execute(f"""
        SELECT CAST(date AS VARCHAR) AS date, code, high, low FROM '{OHLC}'
        WHERE code IN (SELECT DISTINCT code FROM targets) ORDER BY code, date
    """).df()
    series = {c: (g['date'].to_numpy(), g['high'].to_numpy(float), g['low'].to_numpy(float))
              for c, g in px.groupby('code', sort=False)}

    df = compute(targets, series)
    if df.empty:
        print('SKIP: VCP 조건을 충족한 종목 없음')
        return

    n_new = n_same = 0
    for ym, g in df.groupby(df['date'].str[:7]):
        dst = os.path.join(OUT, ym + '.parquet')
        if os.path.exists(dst):
            old = pd.read_parquet(dst)
            old['date'] = old['date'].astype(str).str[:10]
            g = pd.concat([old[~old['date'].isin(set(g['date']))], g])
        g = norm(g)
        if os.path.exists(dst) and norm(pd.read_parquet(dst)).equals(g):
            n_same += 1
            continue
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name, CAST(close AS DOUBLE) AS close,
                         CAST(rs AS UTINYINT) AS rs, in_tpl, CAST(pivot_px AS DOUBLE) AS pivot_px,
                         CAST(dist AS DOUBLE) AS dist, CAST(n_cont AS UTINYINT) AS n_cont,
                         {', '.join(f'CAST(d{k} AS DOUBLE) AS d{k}' for k in range(1, MAX_CONT + 1))},
                         CAST(base_days AS USMALLINT) AS base_days, CAST(tight AS DOUBLE) AS tight, tier
                  FROM g ORDER BY date, code)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        n_new += 1
    last = df[df['date'] == df['date'].max()]
    print(f"OK  VCP -> db/market/vcp/: {len(df):,}행, 날짜 {df['date'].nunique()}개 | "
          f"월 파일 {n_new}개 갱신, {n_same}개 동일 | {last['date'].iloc[0]} "
          f"{len(last)}종목 (템플릿 통과 {int(last['in_tpl'].sum())} · 베이스 중 {len(last) - int(last['in_tpl'].sum())})")


if __name__ == '__main__':
    build(force='--all' in sys.argv[1:])
