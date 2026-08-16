#!/usr/bin/env python3
"""수정주가 DB -> 오닐식 RS 등급 DB (db/market/rs/)

- 각 거래일마다 최근 4개 분기 수익률을 40/20/20/20 가중해 점수를 내고,
  같은 날 전체 대비 백분위로 1~99 등급 산정 (ETF와 일반 종목은 별도 모집단)
- 252거래일(약 1년) 이력이 확보된 날짜만 계산하며, 이미 계산된 날짜는 건너뜀
  (일일 갱신 시 새 날짜 1개만 추가 계산됨)
- 실행: python3 tools/market/build_rs.py        (build_market.py 실행 후)
        python3 tools/market/build_rs.py --all  (전체 재계산)
"""
import sys, os, glob
import duckdb
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
ETF = os.path.join(REPO, 'db', 'etf', '*.parquet')
OUT = os.path.join(REPO, 'db', 'market', 'rs')

OFFSETS = [0, 63, 126, 189, 252]          # 오늘 / 1·2·3·4분기 전 (거래일 기준)
WEIGHTS = [0.4, 0.2, 0.2, 0.2]            # 최근 분기에 가중


def build(force=False):
    con = duckdb.connect()
    con.execute(f"CREATE VIEW prices AS SELECT * FROM '{PRICE}'")
    con.execute(f"CREATE TABLE etfs AS SELECT DISTINCT etf_code AS code FROM '{ETF}'")

    cal = [r[0] for r in con.execute("SELECT DISTINCT date FROM prices ORDER BY date").fetchall()]
    if len(cal) <= OFFSETS[-1]:
        print(f"SKIP: 거래일 {len(cal)}개 — 최소 {OFFSETS[-1] + 1}개 필요")
        return

    done = set()
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(OUT, '*.parquet')))
    if files and not force:
        done = {r[0] for r in con.execute(
            f"SELECT DISTINCT date FROM '{os.path.join(OUT, '*.parquet')}'").fetchall()}

    targets = [cal[i] for i in range(OFFSETS[-1], len(cal)) if cal[i] not in done]
    if not targets:
        print("SKIP: 새로 계산할 날짜 없음")
        return

    idx = {d: i for i, d in enumerate(cal)}
    anchors = pd.DataFrame(
        [(t, k, cal[idx[t] - off]) for t in targets for k, off in enumerate(OFFSETS)],
        columns=['target_date', 'k', 'anchor_date'])
    con.register('anchors', anchors)

    score_expr = ' + '.join(f'{w} * (c{i} / c{i + 1})' for i, w in enumerate(WEIGHTS))
    df = con.execute(f"""
        WITH j AS (
          SELECT a.target_date, p.code, p.name, a.k, p.close
          FROM anchors a JOIN prices p ON p.date = a.anchor_date
        ),
        w AS (
          SELECT target_date, code, any_value(name) AS name,
                 MAX(CASE WHEN k=0 THEN close END) c0, MAX(CASE WHEN k=1 THEN close END) c1,
                 MAX(CASE WHEN k=2 THEN close END) c2, MAX(CASE WHEN k=3 THEN close END) c3,
                 MAX(CASE WHEN k=4 THEN close END) c4
          FROM j GROUP BY target_date, code
        ),
        s AS (
          SELECT target_date AS date, code, name, {score_expr} AS score,
                 code IN (SELECT code FROM etfs) AS is_etf
          FROM w WHERE c0 > 0 AND c1 > 0 AND c2 > 0 AND c3 > 0 AND c4 > 0
        )
        SELECT date, code, name,
               CAST(round((1 - (row_number() OVER (PARTITION BY date, is_etf ORDER BY score DESC) - 1)
                    / GREATEST(count(*) OVER (PARTITION BY date, is_etf) - 1, 1)::DOUBLE) * 98) + 1
                    AS UTINYINT) AS rs
        FROM s ORDER BY date, code
    """).df()
    df['date'] = pd.to_datetime(df['date']).dt.date

    n_new = n_same = 0
    for ym, g in df.groupby(df['date'].map(lambda d: f'{d.year:04d}-{d.month:02d}')):
        dst = os.path.join(OUT, ym + '.parquet')
        if os.path.exists(dst):
            old = pd.read_parquet(dst)
            old['date'] = pd.to_datetime(old['date']).dt.date
            g = pd.concat([old[~old['date'].isin(set(g['date']))], g])
        g = g.sort_values(['date', 'code']).reset_index(drop=True)
        if os.path.exists(dst):
            prev = pd.read_parquet(dst)
            prev['date'] = pd.to_datetime(prev['date']).dt.date
            if prev.sort_values(['date', 'code']).reset_index(drop=True).equals(g):
                n_same += 1
                continue
        con.execute(f"""
            COPY (SELECT CAST(date AS DATE) AS date, code, name, CAST(rs AS UTINYINT) AS rs FROM g)
            TO '{dst}' (FORMAT PARQUET, COMPRESSION SNAPPY)""")
        n_new += 1

    print(f"OK  RS 등급 -> db/market/rs/: {len(df):,}행, 날짜 {len(targets)}개, "
          f"종목 {df['code'].nunique():,}개 | 월 파일 {n_new}개 갱신, {n_same}개 동일")


if __name__ == '__main__':
    build(force='--all' in sys.argv)
