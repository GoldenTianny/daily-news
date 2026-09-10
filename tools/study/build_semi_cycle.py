#!/usr/bin/env python3
"""수정주가·RS·컨센서스 DB -> 반도체 병목 업종 과열 계기판 (study/semi-cycle/data.json)

목적: 메모리 대형주(삼성전자·SK하이닉스)에서 소부장으로 주도권이 넘어간 뒤,
공정별(전공정·후공정·검사·테스트·기판·소재) 업종이 사이클의 어느 단계에 있는지
과거 고점에서 반복된 신호로 매일 점검한다.

업종 지수: 각 업종 종목의 일수익률 동일가중 누적 (가격 DB 시작일 = 1)

신호 (업종별, 최신일 기준)
- 신고가 비율: 종가가 직전 252거래일 최고가 이상인 종목 비율. 40% 이상 과열, 15% 미만 초입
- 목표주가 괴리: 커버 종목의 (목표주가/종가-1) 중앙값. 10% 미만이면 주가가 목표가를 따라잡은 것 → 임박
- 목표주가 상향 폭: 20거래일 전 대비 ±2% 넘게 오른 종목 수 − 내린 종목 수를 커버 수로 나눈 값.
  0 미만(깎는 중) 초입, 50% 초과(앞다퉈 상향) 과열
- 이익 전망 상향 폭: 당해·차년 영업이익 컨센서스의 같은 계산. 0 이하면 경고
- 소형주 과열: 커버리지 없는 종목의 저점 이후 수익률 중앙값이 커버 종목보다 높으면 경고
- 추세 이탈: 업종 지수가 저점 이후 반등 고점을 10거래일 넘게 못 넘으면서 이익 전망은 오르는 중이면 경고
- 대형주 저점 이탈: 대형주 지수가 최근 저점(90거래일 최저)을 깨면 경고 (소부장 손절 기준)

단계: 과열 신호(hot) 0개 초입 / 1개 진행 / 2개 과열 / 3개 이상(또는 2개+약화 1개) 고점 임박.
  과열 신호 없이 약화 신호(warn)만 2개 이상이면 '모멘텀 둔화'(주도 업종 아님)

실행: python3 tools/study/build_semi_cycle.py   (ingest_daily.py 7/8단계)
출력: study/semi-cycle/data.json
"""
import os, glob, json, math, datetime
import pandas as pd
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICE = os.path.join(REPO, 'db', 'market', 'price', '*.parquet')
RS = os.path.join(REPO, 'db', 'market', 'rs', '*.parquet')
CONS = os.path.join(REPO, 'db', 'market', 'consensus', '*.parquet')
EARN = os.path.join(REPO, 'db', 'market', 'earnings', 'consensus', '*.parquet')
OUT = os.path.join(REPO, 'study', 'semi-cycle', 'data.json')

BIG = ['삼성전자', 'SK하이닉스']
SEGMENTS = [
    ('front', '전공정 장비', ['주성엔지니어링', '원익IPS', '유진테크', '테스', '피에스케이', 'HPSP', '케이씨텍', '제우스', '저스템', '로체시스템즈', '뉴파워프라즈마', '예스티', 'GST', '한양이엔지', 'AP시스템', '디아이티', '케이엔제이']),
    ('back', '후공정 장비(HBM·패키징)', ['한미반도체', '피에스케이홀딩스', '이오테크닉스', '하나마이크론', 'SFA반도체', '네패스', '제이티', '프로텍', '아이에스티이', '에스에프에이']),
    ('inspect', '검사·계측', ['인텍플러스', '고영', '펨트론', '기가비스', '오로스테크놀로지', '파크시스템스', '넥스틴', '자비스']),
    ('test', '테스트 부품·장비', ['리노공업', 'ISC', '티에스이', '마이크로컨텍솔', '와이씨', '유니테스트', '엑시콘', '디아이', '티에프이', '오킨스전자', '샘씨엔에스', '테크윙', '두산테스나', '에이팩트', '네오셈', '퀄리타스반도체']),
    ('substrate', '기판(PCB·서브스트레이트)', ['심텍', '해성디에스', '이수페타시스', '대덕전자', '코리아써키트', '비에이치', '티엘비']),
    ('material', '소재·부품', ['솔브레인', '동진쎄미켐', '원익머트리얼즈', '원익QnC', '티씨케이', '에스앤에스텍', '에프에스티', '코미코', '월덱스', '미코', '램테크놀러지', '워트', '비씨엔씨', '하나머티리얼즈', '케이엔더블유', '한솔케미칼', '덕산테코피아']),
]
LOOKBACK = 252
BREADTH_DAYS = 20
LOW_WINDOW = 90
TH = {'nh_hot': 40, 'nh_early': 15, 'gap_near': 10, 'gap_room': 30, 'tp_hot': 50}


def load(pattern, cols=None, since=None):
    fs = sorted(glob.glob(pattern))
    if since:
        fs = [f for f in fs if os.path.basename(f)[:7] >= since]
    df = pd.concat([pd.read_parquet(f, columns=cols) for f in fs], ignore_index=True)
    df['date'] = df['date'].astype(str)
    return df


def r(x, nd=1):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


def breadth(wide, names, k=BREADTH_DAYS):
    """(상향 − 하향)/커버 %, 일별 Series. ±2% 기준"""
    nm = [n for n in names if n in wide.columns]
    if not nm:
        return pd.Series(dtype=float)
    ch = wide[nm] / wide[nm].shift(k) - 1
    up = (ch > 0.02).sum(axis=1); dn = (ch < -0.02).sum(axis=1); n = ch.notna().sum(axis=1)
    return (up - dn) / n.replace(0, np.nan) * 100


def build():
    px = load(PRICE, ['date', 'name', 'close'])
    w = px.pivot_table(index='date', columns='name', values='close')
    TD = list(w.index)
    rs = load(RS, ['date', 'name', 'rs']).pivot_table(index='date', columns='name', values='rs')
    tp = load(CONS, ['date', 'name', 'target_price']).pivot_table(index='date', columns='name', values='target_price')
    ec = load(EARN, ['date', 'name', 'fy', 'op'])
    fy0 = int(TD[-1][:4]); fy1 = fy0 + 1
    e0 = ec[ec.fy == fy0].pivot_table(index='date', columns='name', values='op')
    e1 = ec[ec.fy == fy1].pivot_table(index='date', columns='name', values='op')
    tp_ff = tp.reindex(w.index).ffill()

    rets = w.pct_change()
    hi = w.rolling(LOOKBACK).max().shift(1)

    def seg_index(names):
        return (1 + rets[names].mean(axis=1)).cumprod()

    big_names = [n for n in BIG if n in w.columns]
    big_idx = seg_index(big_names)
    # 대형주 최근 저점(90거래일 최저) — 소부장 손절 기준선
    recent = big_idx.iloc[-LOW_WINDOW:]
    low_date = recent.idxmin(); low_i = TD.index(low_date)
    big_broke_low = bool(big_idx.iloc[-1] < recent.min())

    def series_pack(names):
        nm = [n for n in names if n in w.columns]
        idx = seg_index(nm)
        nh = (w[nm] >= hi[nm]).mean(axis=1) * 100
        cov = [n for n in nm if n in tp.columns]
        gap = ((tp_ff[cov] / w[cov] - 1) * 100).median(axis=1) if cov else pd.Series(index=w.index, dtype=float)
        b_tp = breadth(tp, nm); b0 = breadth(e0, nm); b1 = breadth(e1, nm)
        return nm, idx, nh, cov, gap, b_tp, b0, b1

    def monthly(idx, nh, gap, b_tp, b0, b1):
        m = idx.groupby(idx.index.str[:7]).last()
        out = []
        for mo in m.index:
            if mo < TD[0][:7]:
                continue
            sl = lambda s: s[s.index.str[:7] == mo]
            prev = m.shift(1).get(mo)
            out.append({'m': mo, 'ret': r((m[mo] / prev - 1) * 100) if prev and not np.isnan(prev) else None,
                        'nh_max': r(sl(nh).max()), 'nh_last': r(sl(nh).iloc[-1]) if len(sl(nh)) else None,
                        'gap': r(sl(gap).dropna().iloc[-1]) if len(sl(gap).dropna()) else None,
                        'tp': r(sl(b_tp).dropna().iloc[-1]) if len(sl(b_tp).dropna()) else None,
                        'e0': r(sl(b0).dropna().iloc[-1]) if len(sl(b0).dropna()) else None,
                        'e1': r(sl(b1).dropna().iloc[-1]) if len(sl(b1).dropna()) else None})
        return out

    def last(s):
        s = s.dropna(); return r(s.iloc[-1]) if len(s) else None

    def signals(nm, idx, nh, cov, gap, b_tp, b0, b1):
        i = len(TD) - 1
        ret_low = (w[nm].iloc[i] / w[nm].iloc[low_i] - 1) * 100
        uncov = [n for n in nm if n not in cov]
        cov_ret = r(ret_low[cov].median()) if cov else None
        uncov_ret = r(ret_low[uncov].median()) if uncov else None
        # 추세 이탈: 저점 이후 반등 고점(최고 종가)을 못 넘은 지 며칠
        rally = idx.iloc[low_i:i + 1]
        days_no_high = int(i - TD.index(rally.idxmax()))
        nh_v, gap_v, tp_v, e0_v, e1_v = last(nh), last(gap), last(b_tp), last(b0), last(b1)
        flags = []
        def lvl(name, level, text):
            flags.append({'name': name, 'level': level, 'text': text})
        if nh_v is not None:
            lvl('신고가 비율', 'hot' if nh_v >= TH['nh_hot'] else ('mid' if nh_v >= TH['nh_early'] else 'early'), f'{nh_v:.0f}%')
        if gap_v is not None:
            lvl('목표주가 괴리', 'hot' if gap_v < TH['gap_near'] else ('mid' if gap_v < TH['gap_room'] else 'early'), f'{gap_v:+.0f}%')
        if tp_v is not None:
            lvl('목표주가 상향 폭', 'hot' if tp_v > TH['tp_hot'] else ('mid' if tp_v >= 0 else 'early'), f'{tp_v:+.0f}%')
        if e0_v is not None:
            lvl(f'{fy0}E 이익 전망 상향 폭', 'warn' if e0_v <= 0 else 'ok', f'{e0_v:+.0f}%')
        if e1_v is not None:
            lvl(f'{fy1}E 이익 전망 상향 폭', 'warn' if e1_v <= 0 else 'ok', f'{e1_v:+.0f}%')
        if cov_ret is not None and uncov_ret is not None:
            lvl('소형주 과열(비커버 > 커버)', 'warn' if uncov_ret > cov_ret else 'ok', f'비커버 {uncov_ret:+.0f}% vs 커버 {cov_ret:+.0f}%')
        lvl('추세 이탈(반등 고점 미갱신)', 'warn' if (days_no_high > 10 and (e0_v or 0) > 0) else 'ok', f'{days_no_high}일째')
        hot = sum(1 for f in flags if f['level'] == 'hot')
        warn = sum(1 for f in flags if f['level'] == 'warn')
        # 과열(hot)과 약화(warn)를 분리: 과열이 쌓이면 고점, 과열 없이 약화만 있으면 주도 업종이 아님
        if hot >= 3 or (hot >= 2 and warn >= 1):
            stage = '고점 임박'
        elif hot >= 2:
            stage = '과열'
        elif hot == 1:
            stage = '진행'
        elif warn >= 2:
            stage = '모멘텀 둔화'
        else:
            stage = '초입'
        score = hot
        return {'nh': nh_v, 'gap': gap_v, 'tp': tp_v, 'e0': e0_v, 'e1': e1_v, 'cov_ret': cov_ret, 'uncov_ret': uncov_ret,
                'days_no_high': days_no_high, 'hot': hot, 'warn': warn, 'ret_low': r(ret_low.median()), 'ret20': r(((w[nm].iloc[i] / w[nm].iloc[i - 20] - 1) * 100).median()),
                'gap_hi': r(((w[nm].iloc[i] / w[nm].iloc[-LOOKBACK:].max() - 1) * 100).median()),
                'rs': r(rs[[n for n in nm if n in rs.columns]].iloc[-1].median()) if any(n in rs.columns for n in nm) else None,
                'idx_from_low': r((idx.iloc[i] / idx.iloc[low_i] - 1) * 100), 'idx_from_peak': r((idx.iloc[i] / idx.max() - 1) * 100),
                'peak_date': idx.idxmax(), 'flags': flags, 'score': score, 'stage': stage}

    def stocks(nm, cov):
        i = len(TD) - 1
        out = []
        for n in nm:
            s = w[n]
            if pd.isna(s.iloc[i]):
                continue
            c = lambda wide, k: r((wide[n].iloc[-1] / wide[n].iloc[-1 - k] - 1) * 100) if n in wide.columns and len(wide[n].dropna()) > k else None
            out.append({'name': n, 'close': s.iloc[i], 'ret_low': r((s.iloc[i] / s.iloc[low_i] - 1) * 100), 'ret20': r((s.iloc[i] / s.iloc[i - 20] - 1) * 100),
                        'gap_hi': r((s.iloc[i] / s.iloc[-LOOKBACK:].max() - 1) * 100), 'nh': bool(s.iloc[i] >= hi[n].iloc[i]) if not pd.isna(hi[n].iloc[i]) else False,
                        'rs': int(rs[n].iloc[-1]) if n in rs.columns and not pd.isna(rs[n].iloc[-1]) else None,
                        'tp_gap': r((tp_ff[n].iloc[i] / s.iloc[i] - 1) * 100) if n in cov and not pd.isna(tp_ff[n].iloc[i]) else None,
                        'tp60': c(tp, 60), 'e0_60': c(e0, 60), 'e1_60': c(e1, 60), 'covered': n in cov})
        return sorted(out, key=lambda x: -(x['ret_low'] or -999))

    segs = []
    all_sobu = []
    for key, label, names in SEGMENTS:
        nm, idx, nh, cov, gap, b_tp, b0, b1 = series_pack(names)
        all_sobu += nm
        segs.append({'key': key, 'label': label, 'n': len(nm), 'signals': signals(nm, idx, nh, cov, gap, b_tp, b0, b1),
                     'monthly': monthly(idx, nh, gap, b_tp, b0, b1), 'stocks': stocks(nm, cov)})
    # 소부장 전체
    nm, idx, nh, cov, gap, b_tp, b0, b1 = series_pack(all_sobu)
    sobu = {'key': 'all', 'label': '소부장 전체', 'n': len(nm), 'signals': signals(nm, idx, nh, cov, gap, b_tp, b0, b1),
            'monthly': monthly(idx, nh, gap, b_tp, b0, b1), 'stocks': []}
    sobu_idx = idx
    # 대형주
    nmb, idxb, nhb, covb, gapb, b_tpb, b0b, b1b = series_pack(big_names)
    big = {'key': 'big', 'label': '메모리 대형주(삼성전자·SK하이닉스)', 'n': len(nmb), 'signals': signals(nmb, idxb, nhb, covb, gapb, b_tpb, b0b, b1b),
           'monthly': monthly(idxb, nhb, gapb, b_tpb, b0b, b1b), 'stocks': stocks(nmb, covb)}
    # 상대강도(소부장/대형주) 월말
    rel = (sobu_idx / big_idx); relm = rel.groupby(rel.index.str[:7]).last()
    bigm = big_idx.groupby(big_idx.index.str[:7]).last().pct_change() * 100
    sobm = sobu_idx.groupby(sobu_idx.index.str[:7]).last().pct_change() * 100
    relative = [{'m': m, 'big': r(bigm.get(m)), 'sobu': r(sobm.get(m)), 'rel': r(relm[m], 2)} for m in relm.index if m >= TD[0][:7]]
    # 주도 업종 = 저점 이후 지수 상승률 1위
    leader = max(segs, key=lambda s: s['signals']['idx_from_low'] or -999)['key']

    out = {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'price_last': TD[-1], 'price_first': TD[0], 'fy0': fy0, 'fy1': fy1, 'thresholds': TH,
        'big_low': {'date': low_date, 'broke': big_broke_low, 'from_low': r((big_idx.iloc[-1] / big_idx.iloc[low_i] - 1) * 100),
                    'from_peak': r((big_idx.iloc[-1] / big_idx.max() - 1) * 100), 'peak_date': big_idx.idxmax()},
        'leader': leader, 'big': big, 'sobu': sobu, 'segments': segs, 'relative': relative,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f"OK: {TD[-1]} 기준 → {OUT} ({os.path.getsize(OUT)/1024:.0f}KB) · 주도 업종 {leader} · 대형주 저점 {low_date} 이탈 {big_broke_low}")
    for s in [big, sobu] + segs:
        g = s['signals']
        print(f"  [{s['label']:22s}] 단계 {g['stage']:5s} 점수 {g['score']} · 저점후 {g['idx_from_low']:+.0f}% · 신고가 {g['nh']}% · 괴리 {g['gap']}% · 목표가폭 {g['tp']}% · {fy0}E폭 {g['e0']}%")


if __name__ == '__main__':
    build()
