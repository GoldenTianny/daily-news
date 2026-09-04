#!/usr/bin/env python3
"""수정주가·RS DB -> 마크 미너비니 트렌드 템플릿 판정 DB (db/market/minervini/)

미너비니(Mark Minervini)의 '트렌드 템플릿' 8개 조건을 매 거래일 종목별로 판정한다.
  1. 종가 > 150일선 및 200일선
  2. 150일선 > 200일선
  3. 200일선이 최소 1개월(21거래일) 전보다 상승
  4. 50일선 > 150일선 및 200일선
  5. 종가 > 50일선
  6. 종가가 52주 저점 대비 +30% 이상
  7. 종가가 52주 고점 대비 -25% 이내
  8. RS 등급 70 이상 (db/market/rs, 일반 종목 대비 백분위)
이동평균·52주 고저는 모두 종가 기준 거래일 창(50/150/200/252일).

산출물: db/market/minervini/YYYY-MM.parquet
  date, code, name, close, rs, ma50, ma150, ma200, hi52, lo52,
  flags(UTINYINT: bit i-1 = 조건 i 충족), pass_n(충족 개수), passed(8개 모두),
  streak(연속 충족 거래일 수, passed=false면 0), n_univ(그날 판정한 모집단 종목 수)
- 모집단: 일반 종목만 (build_high52.universe_filter — ETF·ETN·스팩·우선주 제외)
- 저장은 6개 이상 충족한 종목만 (충족 + 근접 종목). 전 종목을 담으면 월 1.4MB로
  매일 재기록되는 파일이 너무 커지므로, streak는 전 종목으로 계산한 뒤 걸러 저장
- 260거래일 이상 이력이 있는 날짜부터 계산, 이미 계산된 달과 내용이 같으면 파일을 다시 쓰지 않음
실행: python3 tools/market/build_minervini.py        (build_rs.py 실행 후)
      python3 tools/market/build_minervini.py --all  (전체 재계산 — 결과는 동일, 강제 재기록)
"""
import sys, os, glob
import duckdb
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'tools', 'study'))
from build_high52 import universe_filter   # noqa: E402

PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
RS = os.path.join(REPO, 'db', 'market', 'rs', '*.parquet')
OUT = os.path.join(REPO, 'db', 'market', 'minervini')

MIN_HISTORY = 260   # 200일선 + 1개월 추세 비교(21일) + 여유
TREND_DAYS = 21     # 200일선 상승 판정 기간(거래일)
LOW_MARGIN = 0.30   # 52주 저점 대비 최소 상승폭
HIGH_MARGIN = 0.25  # 52주 고점 대비 허용 하락폭
RS_MIN = 70

COLS = ['date', 'code', 'name', 'close', 'rs', 'ma50', 'ma150', 'ma200', 'hi52', 'lo52',
        'flags', 'pass_n', 'passed', 'streak', 'n_univ']
KEEP_MIN = 6        # 저장 하한(충족 조건 수)


def compute():
    con = duckdb.connect()
    latest = con.execute(f"SELECT max(date) FROM '{PRICE}'").fetchone()[0]
    snap = con.execute(f"SELECT code, name FROM '{PRICE}' WHERE date = ?", [latest]).df()
    uni = pd.DataFrame({'code': sorted(set(universe_filter(snap)['code']))})
    con.register('uni', uni)
    w = 'PARTITION BY code ORDER BY date'
    df = con.execute(f"""
        WITH p AS (
          SELECT p.date, p.code, p.name, p.close,
                 row_number() OVER ({w}) AS n,
                 avg(close) OVER ({w} ROWS 49 PRECEDING)  AS ma50,
                 avg(close) OVER ({w} ROWS 149 PRECEDING) AS ma150,
                 avg(close) OVER ({w} ROWS 199 PRECEDING) AS ma200,
                 max(close) OVER ({w} ROWS 251 PRECEDING) AS hi52,
                 min(close) OVER ({w} ROWS 251 PRECEDING) AS lo52
          FROM '{PRICE}' p JOIN uni USING (code)
        ),
        q AS (
          SELECT *, lag(ma200, {TREND_DAYS}) OVER ({w}) AS ma200_prev FROM p
        )
        SELECT q.date, q.code, q.name, q.close, r.rs,
               q.ma50, q.ma150, q.ma200, q.hi52, q.lo52, q.ma200_prev
        FROM q LEFT JOIN '{RS}' r ON r.date = q.date AND r.code = q.code
        WHERE q.n >= {MIN_HISTORY} AND q.close > 0
        ORDER BY q.code, q.date
    """).df()

    c = [
        (df['close'] > df['ma150']) & (df['close'] > df['ma200']),
        df['ma150'] > df['ma200'],
        df['ma200'] > df['ma200_prev'],
        (df['ma50'] > df['ma150']) & (df['ma50'] > df['ma200']),
        df['close'] > df['ma50'],
        df['close'] >= df['lo52'] * (1 + LOW_MARGIN),
        df['close'] >= df['hi52'] * (1 - HIGH_MARGIN),
        df['rs'].fillna(0) >= RS_MIN,
    ]
    df['flags'] = sum(ci.astype(int) * (1 << i) for i, ci in enumerate(c))
    df['pass_n'] = sum(ci.astype(int) for ci in c)
    df['passed'] = df['pass_n'] == len(c)
    # 연속 충족 거래일 수 (종목별, 미충족이면 0으로 리셋)
    grp = (~df['passed']).groupby(df['code']).cumsum()
    df['streak'] = df['passed'].astype(int).groupby([df['code'], grp]).cumsum()
    df['date'] = pd.to_datetime(df['date']).dt.date
    df['n_univ'] = df.groupby('date')['code'].transform('size')
    df = df[df['pass_n'] >= KEEP_MIN]
    for k in ('ma50', 'ma150', 'ma200'):
        df[k] = df[k].round(2)
    return df[COLS]


def norm(d):
    d = d.copy()
    d['date'] = d['date'].astype(str).str[:10]
    d['rs'] = d['rs'].astype('float64')
    for k in ('flags', 'pass_n', 'streak', 'n_univ'):
        d[k] = d[k].astype('int64')
    d['passed'] = d['passed'].astype(bool)
    for k in ('close', 'ma50', 'ma150', 'ma200', 'hi52', 'lo52'):
        d[k] = d[k].astype('float64').round(2)
    return d.sort_values(['date', 'code']).reset_index(drop=True)


def build(force=False):
    df = compute()
    if df.empty:
        print("SKIP: 260거래일 이상 이력이 있는 종목 없음")
        return
    os.makedirs(OUT, exist_ok=True)
    n_new = n_same = 0
    con = duckdb.connect()
    for ym, g in df.groupby(df['date'].map(lambda d: f'{d.year:04d}-{d.month:02d}')):
        dst = os.path.join(OUT, ym + '.parquet')
        g = norm(g)
        if os.path.exists(dst) and not force and norm(pd.read_parquet(dst)).equals(g):
            n_same += 1
            continue
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name, CAST(close AS DOUBLE) AS close,
                         CAST(rs AS UTINYINT) AS rs,
                         CAST(ma50 AS DOUBLE) AS ma50, CAST(ma150 AS DOUBLE) AS ma150,
                         CAST(ma200 AS DOUBLE) AS ma200, CAST(hi52 AS DOUBLE) AS hi52,
                         CAST(lo52 AS DOUBLE) AS lo52, CAST(flags AS UTINYINT) AS flags,
                         CAST(pass_n AS UTINYINT) AS pass_n, passed,
                         CAST(streak AS USMALLINT) AS streak,
                         CAST(n_univ AS USMALLINT) AS n_univ
                  FROM g ORDER BY date, code)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        n_new += 1
    last = df[df['date'] == df['date'].max()]
    print(f"OK  미너비니 템플릿 -> db/market/minervini/: {len(df):,}행, "
          f"{df['date'].nunique()}일 | 월 파일 {n_new}개 갱신, {n_same}개 동일 | "
          f"{last['date'].iloc[0]} 충족 {int(last['passed'].sum())}/{int(last['n_univ'].iloc[0]):,}종목")


if __name__ == '__main__':
    build(force='--all' in sys.argv[1:])
