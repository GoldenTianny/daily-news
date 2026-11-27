#!/usr/bin/env python3
"""미너비니 템플릿 종목 메모(db/market/stock_notes.json) 점검 — 일일 DB 반영 때 함께 실행.

  python3 tools/market/notes_todo.py              # 최신 기준일의 할 일 목록 출력
  python3 tools/market/notes_todo.py --json out.json   # 조사할 종목을 JSON으로 저장(code·name·업종·기존 메모)

- 대상: 최신 기준일에 템플릿 8/8 충족 + 7/8 근접 종목 (tools/etf/minervini.html 차트 카드에 뜨는 종목)
- 할 일: 메모가 없는 종목(신규) + 메모 날짜(asof)가 STALE_DAYS일보다 오래된 종목(갱신)
- 메모 형식: notes[Acode] = {name, ind, story, good, bad, asof: 'YYYY-MM-DD'}
  · ind 짧은 업종명 · story 성장 스토리(구조적 성장/실적 턴어라운드/이벤트성 구분) · good 호재 · bad 악재 (각 한 줄, 숫자 포함)
  · 조사 뒤 stock_notes.json의 notes를 갱신하고 최상위 updated도 기준일로 바꾼다
"""
import sys, os, glob, json, datetime
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
NOTES = os.path.join(REPO, 'db', 'market', 'stock_notes.json')
STALE_DAYS = 7


def todo():
    files = sorted(glob.glob(os.path.join(REPO, 'db', 'market', 'minervini', '*.parquet')))
    if not files:
        return None, []
    rows = duckdb.sql(f"""
        select code, name, pass_n, rs, cast(date as varchar) d from '{files[-1]}'
        where date = (select max(date) from '{files[-1]}') and pass_n >= 7
        order by pass_n desc, rs desc nulls last""").fetchall()
    notes = json.load(open(NOTES, encoding='utf-8')) if os.path.exists(NOTES) else {'notes': {}}
    n = notes.get('notes', {})
    base = rows[0][4] if rows else None
    out = []
    for code, name, pass_n, rs, d in rows:
        c = code if code.startswith('A') else 'A' + code
        old = n.get(c)
        asof = (old or {}).get('asof') or (notes.get('updated', '')[:10] if old else '')
        stale = bool(old) and (not asof or (datetime.date.fromisoformat(d[:10]) - datetime.date.fromisoformat(asof[:10])).days >= STALE_DAYS)
        if not old or stale:
            out.append({'code': c, 'name': name, 'template': f'{pass_n}/8', 'rs': rs, 'status': '신규' if not old else '갱신', 'old_note': old})
    return base, out


def report():
    base, out = todo()
    if base is None:
        return
    new = [x['name'] for x in out if x['status'] == '신규']
    old = [x['name'] for x in out if x['status'] == '갱신']
    print(f'[종목 메모] {base[:10]} 템플릿 종목 메모 할 일 — 신규 {len(new)} · 갱신({STALE_DAYS}일 경과) {len(old)}')
    if new: print('  신규: ' + ', '.join(new))
    if old: print('  갱신: ' + ', '.join(old))
    if out: print('  → 호재·악재·성장 스토리를 조사해 db/market/stock_notes.json에 반영(asof = 기준일). 목록 저장: python3 tools/market/notes_todo.py --json 파일')


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--json':
        base, out = todo()
        json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'{base} · {len(out)}종목 → {sys.argv[2]}')
    else:
        report()
