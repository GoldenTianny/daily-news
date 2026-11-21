#!/usr/bin/env node
/* 매집 강도 계산 — node tools/market/flow_strength.js 종목명1 종목명2 ...
 * 매집 강도 = 최근 20거래일 (외국인 + 연기금 + 투신 + 사모) 순매수 합 ÷ 유동시가총액(없으면 시가총액)
 * 출력: 기준일, 매집 강도(%), 20일 합·외국인·기관(연기금+투신+사모)·개인(억 원), 최근 5일 합(억 원), 연속 순매수(+)/순매도(−) 일수,
 *       5일 큰손 비율 = 최근 5거래일 (외국인+연기금+투신+사모) 순매수 ÷ 같은 기간 거래대금(%) — 피라미딩 조건(+2% 이상)에 쓴다
 * 데이터: db/market/flow/·ffmcap/·mcap/ 월별 parquet (SCHEMA.md 참고). 의존성 없이 tools/etf/hyparquet.min.js 사용. */
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const H = new Function(fs.readFileSync(path.join(ROOT, 'tools/etf/hyparquet.min.js'), 'utf8') + ';return hyparquet;')();
const read = async (f) => { const b = fs.readFileSync(f); return H.parquetReadObjects({ file: b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) }); };
const ds = (d) => (d instanceof Date ? d.toISOString().slice(0, 10) : String(d));
const months = (dir, n) => fs.readdirSync(path.join(ROOT, dir)).filter((f) => /^\d{4}-\d{2}\.parquet$/.test(f)).sort().slice(-n).map((f) => path.join(ROOT, dir, f));

(async () => {
  const names = process.argv.slice(2);
  if (!names.length) { console.error('사용법: node tools/market/flow_strength.js 종목명 ...'); process.exit(1); }
  const want = new Set(names);
  let flow = [];
  for (const f of months('db/market/flow', 3)) flow = flow.concat((await read(f)).filter((r) => want.has(r.name)));
  const cap = {}; // 종목별 최신 시가총액, 유동시가총액이 있으면 그것으로 덮어씀
  for (const [dir, col] of [['db/market/mcap', 'mcap'], ['db/market/ffmcap', 'ffmcap']]) {
    for (const f of months(dir, 1)) for (const r of await read(f)) if (want.has(r.name) && r[col] > 0) {
      const c = cap[r.name], d = ds(r.date);
      if (!c || (col === 'ffmcap' && !c.ff) || (c.ff === (col === 'ffmcap') && d >= c.d)) cap[r.name] = { d, v: r[col], ff: col === 'ffmcap' };
    }
  }
  const val = {}; // 종목·날짜별 거래대금
  for (const f of months('db/market/value', 2)) for (const r of await read(f)) if (want.has(r.name)) val[r.name + '|' + ds(r.date)] = r.value;
  const smart = (r) => (r.frgn || 0) + (r.pension || 0) + (r.trust || 0) + (r.pe || 0);
  const sum = (a, f) => a.reduce((s, r) => s + f(r), 0);
  const eok = (x) => Math.round(x / 1e8);
  console.log('종목|기준일|매집강도|20일합(억)|외국인|연기금+투신+사모|개인|5일합|연속일|5일큰손비율');
  for (const n of names) {
    const a = flow.filter((r) => r.name === n).sort((x, y) => (ds(x.date) < ds(y.date) ? -1 : 1));
    if (!a.length || !cap[n]) { console.log(n + '|데이터 없음'); continue; }
    const l20 = a.slice(-20), l5 = a.slice(-5);
    let st = 0;
    for (let i = a.length - 1; i >= 0; i--) { const v = smart(a[i]); if (st >= 0 && v > 0) st++; else if (st <= 0 && v < 0) st--; else break; }
    const s20 = sum(l20, smart);
    console.log([n, ds(a[a.length - 1].date), (s20 / cap[n].v * 100).toFixed(2) + '%', eok(s20), eok(sum(l20, (r) => r.frgn || 0)),
      eok(sum(l20, (r) => (r.pension || 0) + (r.trust || 0) + (r.pe || 0))), eok(sum(l20, (r) => r.retail || 0)), eok(sum(l5, smart)), (st > 0 ? '+' : '') + st,
      (function () { var v = sum(l5, (r) => val[n + '|' + ds(r.date)] || 0); return v > 0 ? (sum(l5, smart) / v * 100).toFixed(1) + '%' : '—'; })()].join('|'));
  }
})();
