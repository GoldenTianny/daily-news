#!/usr/bin/env python3
"""미너비니·RS·와인스타인 RS DB -> 주식 검색기용 일별 스냅샷 DB (db/market/screen/)

주식 검색기(tools/etf/screener.html)가 기준일 하루치 조건을 한 파일로 거를 수 있도록,
일반 종목 전부의 기술적 지표를 거래일별로 한 행씩 모은다. 재무(영업이익)·CANSLIM의
실적 조건은 db/market/earnings 를 브라우저에서 직접 읽어 판정한다.

산출물: db/market/screen/YYYY-MM.parquet
  date, code, name, close, rs(오닐식 RS 등급), mrs(와인스타인 RS),
  mrs_days(와인스타인 RS 제로선 위 연속 거래일 = 돌파 n일째, 제로선 아래면 0,
           이력 시작부터 내내 플러스라 돌파일을 모르면 NULL),
  hi52(252거래일 종가 최고), tpl_flags(미너비니 조건 비트), tpl_n(충족 개수 0~8)
- 모집단·이력: build_minervini.compute 와 동일 (일반 종목 · 260거래일 이상) — 그 결과를
  저장 하한 없이 받아 와인스타인 RS를 붙인다
- 이미 계산된 달과 내용이 같으면 파일을 다시 쓰지 않음
실행: python3 tools/market/build_screen.py        (build_minervini.py 와 같은 시점, ingest_daily 14단계)
      python3 tools/market/build_screen.py --all  (강제 재기록)
"""
import sys, os
import duckdb
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'tools', 'market'))
import build_minervini   # noqa: E402

MRS = os.path.join(REPO, 'db', 'market', 'mrs', '*.parquet')
OUT = os.path.join(REPO, 'db', 'market', 'screen')
COLS = ['date', 'code', 'name', 'close', 'rs', 'mrs', 'mrs_days', 'hi52', 'tpl_flags', 'tpl_n']


def mrs_days():
    """종목별 와인스타인 RS 제로선 위 연속 거래일 (돌파 n일째)."""
    m = duckdb.sql(f"SELECT date, code, mrs FROM '{MRS}' ORDER BY code, date").df()
    pos = m['mrs'] > 0
    run = (~pos).groupby(m['code']).cumsum()                 # 마이너스가 나올 때마다 새 구간
    m['mrs_days'] = pos.astype(int).groupby([m['code'], run]).cumsum()
    # 이력 첫날부터 내내 플러스인 구간은 돌파일을 알 수 없음 → NULL
    never_neg = run == 0
    m['mrs_days'] = m['mrs_days'].astype('float64').mask(never_neg & pos)
    m['date'] = pd.to_datetime(m['date']).dt.date
    return m[['date', 'code', 'mrs', 'mrs_days']]


def compute():
    df = build_minervini.compute(keep_min=0)
    df = df.rename(columns={'flags': 'tpl_flags', 'pass_n': 'tpl_n'})
    df = df.merge(mrs_days(), on=['date', 'code'], how='left')
    return df[COLS]


def norm(d):
    d = d.copy()
    d['date'] = d['date'].astype(str).str[:10]
    for k in ('rs', 'mrs_days'):
        d[k] = d[k].astype('float64')
    d['mrs'] = d['mrs'].astype('float32').round(2).astype('float64')
    for k in ('tpl_flags', 'tpl_n'):
        d[k] = d[k].astype('int64')
    for k in ('close', 'hi52'):
        d[k] = d[k].astype('float64').round(2)
    return d[COLS].sort_values(['date', 'code']).reset_index(drop=True)


def build(force=False):
    df = compute()
    if df.empty:
        print('SKIP: 260거래일 이상 이력이 있는 종목 없음')
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
        con.register('g', g)
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name, CAST(close AS DOUBLE) AS close,
                         CAST(rs AS UTINYINT) AS rs, CAST(mrs AS FLOAT) AS mrs,
                         CAST(mrs_days AS USMALLINT) AS mrs_days, CAST(hi52 AS DOUBLE) AS hi52,
                         CAST(tpl_flags AS UTINYINT) AS tpl_flags, CAST(tpl_n AS UTINYINT) AS tpl_n
                  FROM g ORDER BY date, code)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        con.unregister('g')
        n_new += 1
    last = df[df['date'] == df['date'].max()]
    print(f"OK  주식 검색기 스냅샷 -> db/market/screen/: {len(df):,}행, {df['date'].nunique()}일 | "
          f"월 파일 {n_new}개 갱신, {n_same}개 동일 | {last['date'].iloc[0]} {len(last):,}종목")


if __name__ == '__main__':
    build(force='--all' in sys.argv[1:])
