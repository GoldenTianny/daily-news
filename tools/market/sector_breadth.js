#!/usr/bin/env node
/* 업종 강세 비율 — node tools/market/sector_breadth.js 종목명1 종목명2 ...
 * 강한 종목 = RS 80 이상 + 종가가 52주 종가 고점 대비 −10% 이내 (db/market/screen 최신일)
 * 업종 강세 비율 = 같은 업종(db/market/industry.json, 네이버 업종 코드)에서 자기 자신을 뺀 강한 종목 수 ÷ 업종 종목 수(자기 제외)
 * 상대 강세 = 업종 강세 비율 ÷ 시장 전체 강한 종목 비율. 하락장에선 모든 업종 비율이 낮아지므로 시장 대비로 본다.
 * 매수 규칙(11/23 백테스트, 최종 규칙 돌파 388건): 상대 강세 1배 미만(업종이 시장 평균보다 약함)이면 사지 않는다 — 1배 이상 +0.85R vs 미만 +0.40R. */
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const H = new Function(fs.readFileSync(path.join(ROOT, 'tools/etf/hyparquet.min.js'), 'utf8') + ';return hyparquet;')();
const read = async (f) => { const b = fs.readFileSync(f); return H.parquetReadObjects({ file: b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) }); };
const ds = (d) => (d instanceof Date ? d.toISOString().slice(0, 10) : String(d));
(async () => {
  const names = process.argv.slice(2);
  if (!names.length) { console.error('사용법: node tools/market/sector_breadth.js 종목명 ...'); process.exit(1); }
  const ind = JSON.parse(fs.readFileSync(path.join(ROOT, 'db/market/industry.json'), 'utf8')).map;
  const dir = path.join(ROOT, 'db/market/screen');
  const f = fs.readdirSync(dir).filter((x) => /^\d{4}-\d{2}\.parquet$/.test(x)).sort().pop();
  const rows = await read(path.join(dir, f));
  const last = rows.map((r) => ds(r.date)).sort().pop();
  const day = rows.filter((r) => ds(r.date) === last);
  const strong = (r) => r.rs >= 80 && r.hi52 > 0 && r.close >= 0.9 * r.hi52;
  const mkt = day.filter(strong).length / day.length * 100;
  const by = {};
  for (const r of day) { const k = ind[r.code]; if (!k) continue; (by[k] = by[k] || []).push(r); }
  console.log('기준일 ' + last + ' · 시장 전체 강한 종목 ' + mkt.toFixed(1) + '% · 종목|업종코드|업종 종목수|강한 종목(자기 제외)|업종 비율|시장 대비|판정|같은 업종 강한 종목 예');
  for (const n of names) {
    const me = day.find((r) => r.name === n);
    if (!me) { console.log(n + '|스크린 DB에 없음'); continue; }
    const k = ind[me.code]; const g = (by[k] || []).filter((r) => r.code !== me.code);
    const s = g.filter(strong); const pct = g.length ? s.length / g.length * 100 : 0;
    const rel = mkt > 0 ? pct / mkt : 0;
    const verdict = rel < 1 ? '업종이 시장보다 약함 — 매수 안 함' : rel >= 2 ? '업종 강세 — 우선' : '통과';
    const ex = s.sort((a, b) => b.rs - a.rs).slice(0, 5).map((r) => r.name).join(', ');
    console.log([n, k || '—', g.length + 1, s.length, pct.toFixed(1) + '%', rel.toFixed(1) + '배', verdict, ex].join('|'));
  }
})();
