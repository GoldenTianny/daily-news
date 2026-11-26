#!/usr/bin/env python3
"""일일브리프 기사 하단 '종목 차트' 생성기.

기사에 언급된 상장 종목의 캔들 차트(최근 150거래일 + 이동평균·추세선)를 기사 안에서 펼쳐 볼 수 있게 한다.
- 기사마다 <div class="stock-charts" data-stocks='[{"name":..,"code":..}]'> 블록을 좋아요 버튼 위에 넣고
  /assets/newschart.js 를 연결한다 (누르면 차트가 펼쳐지고, 상세는 ETF 검색기 종목 화면으로 연결).
- 차트 자료는 종목별 작은 JSON(db/newschart/<code>.json)으로 미리 만들어 둔다.
  (월별 Parquet 13개월치 ≈ 6MB를 독자 폰이 받지 않도록 — 종목당 약 10KB)

사용:
  python3 tools/news_stock_charts.py archive/2026-11-27.html --map stocks.json
      stocks.json = {"3": ["삼성전자", "SK하이닉스"], "19": ["삼성SDI", "삼성전기"]}  (기사 번호: 종목명 목록)
      기사 블록 삽입(이미 있으면 교체) + 차트 JSON 생성
  python3 tools/news_stock_charts.py archive/2026-11-27.html
      HTML에 이미 있는 블록 기준으로 차트 JSON만 다시 생성
종목명은 수정주가 DB의 종목명과 정확히 같아야 한다(코드는 자동 조회).
"""
import sys, os, re, json, glob, argparse, html as H
import pyarrow.parquet as pq

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICE = os.path.join(REPO, 'db', 'market', 'price')
OHLC = os.path.join(REPO, 'db', 'market', 'ohlc')
OUT = os.path.join(REPO, 'db', 'newschart')
BARS, PRE = 150, 120          # 화면 거래일 수, 이동평균(120일선)용 앞쪽 종가 수
SCRIPT = '<script src="/assets/newschart.js" defer></script>'


def months(n):
    return sorted(os.path.basename(f)[:7] for f in glob.glob(os.path.join(PRICE, '*.parquet')))[-n:]


def load(kind_dir, mos, codes, cols):
    rows = []
    for mo in mos:
        f = os.path.join(kind_dir, mo + '.parquet')
        if os.path.exists(f):
            t = pq.read_table(f, columns=['date', 'code', 'name'] + cols).to_pandas()
            rows.append(t[t.code.isin(codes)] if codes is not None else t)
    import pandas as pd
    return pd.concat(rows) if rows else None


def resolve(names):
    df = load(PRICE, months(2), None, ['close'])
    last = df.sort_values('date').drop_duplicates('name', keep='last')
    m = dict(zip(last.name, last.code))
    miss = [n for n in names if n not in m]
    if miss:
        sys.exit('수정주가 DB에 없는 종목명: ' + ', '.join(miss))
    return {n: m[n] for n in names}


def build_json(codes):
    os.makedirs(OUT, exist_ok=True)
    mos = months(14)
    p = load(PRICE, mos, codes, ['close'])
    o = load(OHLC, mos[-9:], codes, ['open', 'high', 'low'])
    for code in codes:
        s = p[(p.code == code) & (p.close > 0)].sort_values('date')
        if s.empty:
            print('[경고] 가격 없음', code); continue
        d = s.date.astype(str).str[:10].tolist(); c = s.close.tolist()
        q = o[o.code == code]
        qm = {str(r.date)[:10]: [r.open, r.high, r.low] for r in q.itertuples() if r.open > 0 and r.high > 0 and r.low > 0}
        show = list(zip(d, c))[-BARS:]
        pre = c[max(0, len(c) - BARS - PRE):max(0, len(c) - BARS)]
        js = {'name': s.name.iloc[-1], 'code': code, 'asof': d[-1],
              'price': [[a, round(b, 2)] for a, b in show],
              'ohlc': {a: [round(x, 2) for x in qm[a]] for a, _ in show if a in qm},
              'pre': [round(x, 2) for x in pre]}
        with open(os.path.join(OUT, code + '.json'), 'w', encoding='utf-8') as f:
            json.dump(js, f, ensure_ascii=False, separators=(',', ':'))
        print(f'  {js["name"]}({code}) {len(show)}봉 · 기준 {d[-1]}')


def block(stocks):
    data = H.escape(json.dumps([{'name': n, 'code': c} for n, c in stocks], ensure_ascii=False), quote=True)
    return f'    <!-- 종목 차트 -->\n    <div class="stock-charts" data-stocks="{data}"></div>\n'


def inject(path, mapping):
    s = open(path, encoding='utf-8').read()
    s = re.sub(r'    <!-- 종목 차트 -->\n    <div class="stock-charts" data-stocks="[^"]*"></div>\n', '', s)
    names = sorted({n for v in mapping.values() for n in v})
    codes = resolve(names)
    for no, ns in mapping.items():
        a = s.index(f'<article class="article" id="a{no}">')
        k = s.index('    <!-- 좋아요 + 공유 -->', a)
        assert k < s.index('</article>', a), f'기사 {no} 구조 확인 필요'
        s = s[:k] + block([(n, codes[n]) for n in ns]) + s[k:]
    if SCRIPT not in s:
        s = s.replace('</body>', SCRIPT + '\n</body>', 1)
    open(path, 'w', encoding='utf-8').write(s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('html'); ap.add_argument('--map')
    a = ap.parse_args()
    if a.map:
        s = inject(a.html, json.load(open(a.map, encoding='utf-8')))
    else:
        s = open(a.html, encoding='utf-8').read()
    codes = set()
    for m in re.findall(r'class="stock-charts" data-stocks="([^"]*)"', s):
        codes |= {x['code'] for x in json.loads(H.unescape(m))}
    print(f'종목 {len(codes)}개 차트 JSON 생성')
    build_json(sorted(codes))


if __name__ == '__main__':
    main()
