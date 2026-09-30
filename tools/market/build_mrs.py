#!/usr/bin/env python3
"""수정주가·지수 DB -> 와인스타인 RS(맨스필드 RS) DB (db/market/mrs/)

스탠 와인스타인이 쓰는 상대강도선. 오닐식 RS 등급(db/market/rs, 종목 간 백분위)과
달리 **시장지수 대비 비율의 추세**를 본다.
- 비율 = 종목 수정주가 ÷ 코스피 종가 (일봉)
- 기준선 = 비율의 252거래일(약 1년) 이동평균
- mrs = (비율 ÷ 기준선 − 1) × 100  → 0 = 지난 1년 평균만큼 시장을 따라감,
  플러스 = 평소보다 시장을 이기는 중, 마이너스 = 뒤지는 중.
  제로선을 아래에서 위로 넘는 순간이 와인스타인의 매수 관문(2단계 진입 확인).
- 대상: 가격 DB의 모든 종목·ETF 중 252거래일 이력이 있는 것 (코스닥 종목도 코스피 대비)
- 매 실행마다 전체를 다시 계산하되(수 초), 내용이 바뀐 월 파일만 다시 씀
- 실행: python3 tools/market/build_mrs.py   (build_market.py · build_index.py 실행 후, ingest_daily 8단계)
"""
import os, glob, sys
import duckdb
import pandas as pd
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
INDEX = os.path.join(REPO, 'db', 'market', 'index', '*.parquet')
OUT = os.path.join(REPO, 'db', 'market', 'mrs')
WINDOW = 252          # 기준선 이동평균 길이(거래일)
BENCH = 'IKS900'      # 코스피


def build(force=False):
    con = duckdb.connect()
    px = con.execute(f"SELECT date, code, name, close FROM '{PRICE}' WHERE close > 0").df()
    ix = con.execute(f"SELECT date, close FROM '{INDEX}' WHERE code = '{BENCH}'").df()
    if px.empty or ix.empty:
        print('SKIP: 가격 또는 지수 DB 없음'); return
    px['date'] = pd.to_datetime(px['date']); ix['date'] = pd.to_datetime(ix['date'])
    wide = px.pivot_table(index='date', columns='code', values='close').sort_index()
    bench = ix.set_index('date')['close'].sort_index().reindex(wide.index).ffill()
    if len(wide) <= WINDOW:
        print(f'SKIP: 거래일 {len(wide)}개 — 최소 {WINDOW + 1}개 필요'); return
    ratio = wide.div(bench, axis=0)
    base = ratio.rolling(WINDOW, min_periods=WINDOW).mean()
    mrs = (ratio / base - 1) * 100
    mrs = mrs.iloc[WINDOW:]                       # 기준선이 확보된 날짜만
    long = mrs.stack().reset_index()
    long.columns = ['date', 'code', 'mrs']
    long = long[np.isfinite(long['mrs'])]
    names = px.sort_values('date').groupby('code')['name'].last()
    long['name'] = long['code'].map(names)
    long['mrs'] = long['mrs'].round(2).astype('float32')
    long['date'] = long['date'].dt.date

    def norm(d):
        d = d[['date', 'code', 'name', 'mrs']].copy()
        d['date'] = d['date'].astype(str).str[:10]
        d['code'] = d['code'].astype(object); d['name'] = d['name'].astype(object)
        d['mrs'] = d['mrs'].astype('float32').round(2)
        return d.sort_values(['date', 'code']).reset_index(drop=True)

    os.makedirs(OUT, exist_ok=True)
    n_new = n_same = 0
    for ym, g in long.groupby(long['date'].map(lambda d: f'{d.year:04d}-{d.month:02d}')):
        dst = os.path.join(OUT, ym + '.parquet')
        g = g.sort_values(['date', 'code']).reset_index(drop=True)
        if os.path.exists(dst) and not force and norm(pd.read_parquet(dst)).equals(norm(g)):
            n_same += 1
            continue
        con.register('g', g)
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name, CAST(mrs AS FLOAT) AS mrs FROM g)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        con.unregister('g')
        n_new += 1
    last = long['date'].max()
    print(f"OK  와인스타인 RS -> db/market/mrs/: {len(long):,}행, {long['date'].min()}~{last}, "
          f"종목 {long['code'].nunique():,}개 | 월 파일 {n_new}개 갱신, {n_same}개 동일")


if __name__ == '__main__':
    build(force='--all' in sys.argv)
