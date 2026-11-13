// 종목 보조 패널 공용 모듈 — 미너비니 차트 모아보기에서 캔들 차트를 옆으로 넘기면 나오는 화면
//  StockPanels.line(el, o)     최근 1년 수정주가 · 목표주가 컨센서스 · RS 등급 · 와인스타인 RS (ETF 검색기 종목 화면의 선 차트와 같은 구성)
//  StockPanels.earnings(el, o) 연도별 영업이익·증가율(연도를 누르면 분기) + 연간 영업이익 컨센서스 추이
// 여러 개를 한 페이지에 그릴 수 있도록 id 없이 컨테이너(el) 안에서만 동작한다.
(function () {
'use strict';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const fmt = v => Math.round(v).toLocaleString();
const fmtOp = v => {             // 천원 -> 조/억
  const abs = Math.abs(v);
  if (abs >= 1e11) return (v / 1e9).toFixed(1) + '조원';
  if (abs >= 1e9) return (v / 1e9).toFixed(2) + '조원';
  if (abs >= 1e5) return Math.round(v / 1e5).toLocaleString() + '억원';
  return Math.round(v / 10).toLocaleString() + '만원';
};
const growthCell = (cur, prev) => {   // [표시문자열, 색상클래스]
  if (prev == null) return ['-', 'flat'];
  if (prev > 0 && cur > 0) {
    const g = (cur / prev - 1) * 100;
    return [(g >= 0 ? '+' : '') + (Math.abs(g) >= 100 ? g.toFixed(0) : g.toFixed(1)) + '%', g > 0.05 ? 'up' : g < -0.05 ? 'down' : 'flat'];
  }
  if (prev <= 0 && cur > 0) return ['흑전', 'up'];
  if (prev > 0 && cur <= 0) return ['적전', 'down'];
  return ['적지', 'flat'];
};
const atOrBefore = (arr, d) => { let v = null; for (const p of arr) { if (p[0] <= d) v = p[1]; else break; } return v; };

const css = document.createElement('style');
css.textContent =
  '.sp-title{font-weight:600;font-size:15px;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}' +
  '.sp-sub{font-size:12px;color:#999;margin:2px 0 8px;line-height:1.6}' +
  '.sp-wrap{position:relative}.sp-wrap svg{display:block;width:100%}' +
  '.sp-tip{position:absolute;pointer-events:none;display:none;z-index:10;background:rgba(26,35,126,.94);color:#fff;' +
    'font-size:12px;padding:6px 10px;border-radius:6px;white-space:nowrap;line-height:1.5;text-align:left}' +
  '.sp-empty{padding:40px 10px;text-align:center;color:#aaa;font-size:13px}' +
  '.sp-earn{border-collapse:collapse;margin-top:2px;width:auto;min-width:0}' +
  '.sp-earn tr{border-bottom:1px solid #f0f2f7}' +
  '.sp-earn td{padding:4px 0;font-size:13px;border-bottom:none;background:none;text-align:left;white-space:nowrap}' +
  '.sp-earn td.yr{color:#888;font-weight:600;font-size:12px;padding-right:16px}' +
  '.sp-earn td.yr .e{color:#3f51b5}' +
  '.sp-earn td.op{text-align:right;color:#555;font-variant-numeric:tabular-nums;min-width:86px}' +
  '.sp-earn td.op .unit{color:#aaa;font-size:11px}' +
  '.sp-earn td.gv{text-align:right;font-weight:700;font-variant-numeric:tabular-nums;min-width:72px;padding-left:6px}' +
  '.sp-earn td.gv.up{color:#c62828}.sp-earn td.gv.down{color:#2a5ca8}.sp-earn td.gv.flat{color:#888}' +
  '.sp-earn td.chev{color:#9fa8da;font-size:11px;padding-left:8px}' +
  '.sp-earn tr.yrow{cursor:pointer}.sp-earn tr.yrow:hover td{background:#f5f7fb}.sp-earn tr.on td{background:#e8eaf6}' +
  '.sp-earn tr.qrow{border-bottom:none}.sp-earn tr.qrow td{background:#f8f9fd;font-size:12px;padding:2px 0}' +
  '.sp-earn tr.qrow td.yr{color:#aab;font-weight:500;padding-left:14px}' +
  '.sp-cols{display:flex;flex-wrap:wrap;gap:8px 28px;align-items:flex-start}.sp-cols>div:last-child{flex:1 1 340px;min-width:0}';
document.head.appendChild(css);

// ===== 1년 선 차트 =====
//  o.name · o.date 기준일 · o.price [[d, 종가]] · o.tp [[d, 목표주가]] · o.rs [[d, 등급]] · o.mrs [[d, 값]] (모두 오름차순, 없으면 빈 배열)
function line(el, o) {
  const price = o.price || [], tp = o.tp || [];
  const rs = o.rs && o.rs.length > 1 ? o.rs : [], mrs = o.mrs && o.mrs.length > 1 ? o.mrs : [];
  if (price.length < 2) { el.innerHTML = '<div class="sp-empty">가격 데이터가 없습니다</div>'; return; }
  const from = (parseInt(o.date.slice(0, 4)) - 1) + o.date.slice(4);
  const W = Math.max(300, o.width || el.clientWidth);
  const MP = mrs.length ? 84 : 0;
  const H = (o.height || 300) + MP, L = 62, R = (rs.length || mrs.length) ? 32 : 14, T = 16, B = 26;
  const mainB = H - B - MP;
  const x0 = Date.parse(from), x1 = Date.parse(o.date);
  let vmin = Infinity, vmax = -Infinity;
  for (const [, v] of price) { if (v < vmin) vmin = v; if (v > vmax) vmax = v; }
  for (const [, v] of tp) { if (v < vmin) vmin = v; if (v > vmax) vmax = v; }
  const pad = (vmax - vmin) * 0.06 || vmax * 0.05;
  vmin -= pad; vmax += pad;
  const X = d => L + (Date.parse(d) - x0) / (x1 - x0) * (W - L - R);
  const Y = v => T + (vmax - v) / (vmax - vmin) * (mainB - T);
  const path = (pts, yf) => pts.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + yf(p[1]).toFixed(1)).join('');

  let g = '';
  for (let i = 0; i <= 4; i++) {
    const v = vmin + (vmax - vmin) * i / 4, y = Y(v).toFixed(1);
    g += '<line x1="' + L + '" y1="' + y + '" x2="' + (W - R) + '" y2="' + y + '" stroke="#eee"/>' +
      '<text x="' + (L - 8) + '" y="' + y + '" text-anchor="end" dominant-baseline="middle" font-size="11" fill="#999">' + fmt(v) + '</text>';
  }
  // X 라벨: 격월 1일
  let ym = from.slice(0, 7), k = 0;
  while (ym <= o.date.slice(0, 7)) {
    const t = Date.parse(ym + '-01');
    if (k % 2 === 1 && t >= x0 && t <= x1) g += '<text x="' + X(ym + '-01').toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="11" fill="#999">' + ym.slice(2).replace('-', '.') + '</text>';
    const y = parseInt(ym.slice(0, 4)), m = parseInt(ym.slice(5));
    ym = (m === 12 ? y + 1 : y) + '-' + String(m === 12 ? 1 : m + 1).padStart(2, '0'); k++;
  }
  let lines = '<path d="' + path(price, Y) + '" fill="none" stroke="#3f51b5" stroke-width="1.8"/>';
  if (tp.length > 1) lines += '<path d="' + path(tp, Y) + '" fill="none" stroke="#c62828" stroke-width="1.6" stroke-dasharray="5 3"/>';

  let rsNow = null;
  if (rs.length) {                 // RS 등급 — 우측 0~100 고정축, 80·50 기준선
    const rsTop = T + 6, rsBot = mainB - 6, YR = v => rsBot - v / 100 * (rsBot - rsTop);
    rsNow = rs[rs.length - 1][1];
    for (const u of [0, 50, 80, 100]) {
      const y = YR(u).toFixed(1);
      if (u === 50 || u === 80) g += '<line x1="' + L + '" y1="' + y + '" x2="' + (W - R) + '" y2="' + y + '" stroke="#2e7d32" stroke-opacity="' + (u === 80 ? 0.4 : 0.2) + '" stroke-dasharray="4 4"/>';
      g += '<text x="' + (W - R + 5) + '" y="' + y + '" dominant-baseline="middle" font-size="10" fill="#2e7d32"' + (u === 80 ? ' font-weight="700"' : ' opacity="0.75"') + '>' + u + '</text>';
    }
    lines = '<path d="' + path(rs, YR) + '" fill="none" stroke="#2e7d32" stroke-width="1.5" opacity="0.9"/>' +
      '<text x="' + (L + 4) + '" y="' + (YR(rs[0][1]) - 7).toFixed(1) + '" font-size="10" font-weight="700" fill="#2e7d32" opacity="0.9">RS</text>' + lines;
  }
  let mrsNow = null;
  if (mrs.length) {                // 와인스타인 RS 패널 — 제로선 위 = 시장을 이기는 중
    const pT = mainB + 16, pB = H - B - 4, mid = (pT + pB) / 2;
    let m = 10; for (const [, v] of mrs) if (Math.abs(v) > m) m = Math.abs(v);
    m = Math.ceil(m / 10) * 10;
    const YM = v => mid - v / m * (pB - pT) / 2;
    mrsNow = mrs[mrs.length - 1][1];
    g += '<line x1="' + L + '" y1="' + (pT - 8) + '" x2="' + (W - R) + '" y2="' + (pT - 8) + '" stroke="#eee"/>' +
      '<line x1="' + L + '" y1="' + mid.toFixed(1) + '" x2="' + (W - R) + '" y2="' + mid.toFixed(1) + '" stroke="#8e24aa" stroke-opacity="0.55" stroke-dasharray="4 3"/>';
    for (const u of [m, 0, -m]) g += '<text x="' + (W - R + 5) + '" y="' + YM(u).toFixed(1) + '" dominant-baseline="middle" font-size="10" fill="#8e24aa" opacity="' + (u === 0 ? '1' : '0.7') + '">' + (u > 0 ? '+' : '') + u + '</text>';
    let area = '';
    for (const p of mrs) area += (area ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + YM(Math.max(0, p[1])).toFixed(1);
    area += 'L' + X(mrs[mrs.length - 1][0]).toFixed(1) + ' ' + mid.toFixed(1) + 'L' + X(mrs[0][0]).toFixed(1) + ' ' + mid.toFixed(1) + 'Z';
    lines += '<path d="' + area + '" fill="#8e24aa" fill-opacity="0.12"/><path d="' + path(mrs, YM) + '" fill="none" stroke="#8e24aa" stroke-width="1.5"/>' +
      '<text x="' + (L + 4) + '" y="' + (pT - 1) + '" font-size="10" font-weight="700" fill="#8e24aa">와인스타인 RS (0 = 1년 평균)</text>';
  }

  const last = price[price.length - 1][1], lastTp = tp.length ? tp[tp.length - 1][1] : null;
  const legend = '<span style="color:#3f51b5">&#9644;</span> 수정주가 ' + fmt(last) +
    (tp.length > 1 ? ' &nbsp;<span style="color:#c62828">&#9476;</span> 목표주가 ' + fmt(lastTp) + ' (괴리율 ' + ((lastTp / last - 1) * 100).toFixed(1) + '%)' : ' (목표주가 컨센서스 없음)') +
    (rs.length ? ' &nbsp;<span style="color:#2e7d32">&#9644;</span> RS 등급 <b style="color:' + (rsNow >= 80 ? '#2e7d32' : rsNow >= 50 ? '#666' : '#c62828') + '">' + rsNow + '</b>' : '') +
    (mrs.length ? ' &nbsp;<span style="color:#8e24aa">&#9644;</span> 와인스타인 RS <b style="color:' + (mrsNow > 0 ? '#8e24aa' : '#999') + '">' + (mrsNow > 0 ? '+' : '') + mrsNow.toFixed(1) + '</b>' : '');

  el.innerHTML = '<div class="sp-title">' + (o.titleHtml || esc(o.name)) + '<span style="font-weight:500;font-size:12px;color:#888">최근 1년 · 목표주가 · RS</span></div>' +
    '<div class="sp-sub">' + legend + '</div>' +
    '<div class="sp-wrap"><svg viewBox="0 0 ' + W + ' ' + H + '" style="aspect-ratio:' + W + '/' + H + ';height:auto">' + g + lines +
    '<line class="sp-cross" x1="0" y1="' + T + '" x2="0" y2="' + (H - B) + '" stroke="#bbb" stroke-dasharray="2 2" style="display:none"/></svg><div class="sp-tip"></div></div>';

  const svg = el.querySelector('svg'), tip = el.querySelector('.sp-tip'), cross = el.querySelector('.sp-cross');
  const show = clientX => {
    const r = svg.getBoundingClientRect(), mx = (clientX - r.left) / r.width * W;
    if (mx < L || mx > W - R) { tip.style.display = 'none'; cross.style.display = 'none'; return; }
    let best = price[0];
    for (const p of price) if (Math.abs(X(p[0]) - mx) < Math.abs(X(best[0]) - mx)) best = p;
    const d = best[0], tpv = atOrBefore(tp, d), rsv = rs.length ? atOrBefore(rs, d) : null, mv = mrs.length ? atOrBefore(mrs, d) : null;
    cross.setAttribute('x1', X(d)); cross.setAttribute('x2', X(d)); cross.style.display = '';
    tip.innerHTML = d + '<br>수정주가 ' + fmt(best[1]) + '원' + (tpv ? '<br>목표주가 ' + fmt(tpv) + '원' : '') +
      (rsv != null ? '<br>RS 등급 ' + rsv : '') + (mv != null ? '<br>와인스타인 RS ' + (mv > 0 ? '+' : '') + mv.toFixed(1) : '');
    tip.style.display = 'block';
    const px = X(d) / W * r.width;
    tip.style.left = Math.max(4, Math.min(px + 12, r.width - tip.offsetWidth - 4)) + 'px';
    tip.style.top = '4px';
  };
  svg.addEventListener('mousemove', ev => show(ev.clientX));
  svg.addEventListener('mouseleave', () => { tip.style.display = 'none'; cross.style.display = 'none'; });
}

// ===== 연간 영업이익 컨센서스 추이 선 차트 =====  res = {fys:[fy], byFy: Map(fy -> [[date, op]])}
const CONS_COLORS = ['#3f51b5', '#00897b', '#e65100'];
function consChart(box, res, width) {
  const fys = res.fys;
  const W = Math.max(300, width || box.clientWidth), H = 204, L = 66, R = 14, T = 12, B = 30;
  let x0 = Infinity, x1 = -Infinity, vmin = Infinity, vmax = -Infinity;
  for (const fy of fys) for (const [d, v] of res.byFy.get(fy)) {
    const t = Date.parse(d);
    if (t < x0) x0 = t; if (t > x1) x1 = t;
    if (v < vmin) vmin = v; if (v > vmax) vmax = v;
  }
  const pad = (vmax - vmin) * 0.1 || Math.abs(vmax) * 0.05 || 1;
  vmin -= pad; vmax += pad;
  const X = d => L + (Date.parse(d) - x0) / Math.max(x1 - x0, 1) * (W - L - R);
  const Y = v => T + (vmax - v) / (vmax - vmin) * (H - T - B);
  let g = '';
  for (let i = 0; i <= 3; i++) {
    const v = vmin + (vmax - vmin) * i / 3, yy = Y(v).toFixed(1);
    g += '<line x1="' + L + '" y1="' + yy + '" x2="' + (W - R) + '" y2="' + yy + '" stroke="#eee"/>' +
      '<text x="' + (L - 8) + '" y="' + yy + '" text-anchor="end" dominant-baseline="middle" font-size="10" fill="#999">' + fmtOp(v) + '</text>';
  }
  // X축: 분기 첫 달(1·4·7·10월) 라벨
  const a = new Date(x0), b = new Date(x1);
  for (let y = a.getUTCFullYear(), m = a.getUTCMonth(); y < b.getUTCFullYear() || (y === b.getUTCFullYear() && m <= b.getUTCMonth()); m === 11 ? (y++, m = 0) : m++) {
    if (m % 3 !== 0) continue;
    const d = y + '-' + String(m + 1).padStart(2, '0') + '-01', t = Date.parse(d);
    if (t < x0 || t > x1) continue;
    g += '<text x="' + X(d).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="10" fill="#999">' + d.slice(2, 7).replace('-', '.') + '</text>';
  }
  let lg = '';
  fys.forEach((fy, i) => {
    const s = res.byFy.get(fy), c = CONS_COLORS[i % CONS_COLORS.length], first = s[0], last = s[s.length - 1];
    g += '<path d="' + s.map((p, j) => (j ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('') + '" fill="none" stroke="' + c + '" stroke-width="1.8"/>';
    const ch = first[1] > 0 && last[1] > 0 ? (last[1] / first[1] - 1) * 100 : null;
    lg += '<span style="white-space:nowrap"><b style="color:' + c + '">&#9644; ' + fy + 'E</b> ' + fmtOp(last[1]) +
      (ch == null ? '' : ' (' + (ch >= 0 ? '+' : '') + ch.toFixed(1) + '%)') + '</span> &nbsp;';
  });
  box.innerHTML = '<div class="sp-sub" style="color:#666;margin:0 0 4px">' + lg + '</div><div class="sp-wrap"><svg viewBox="0 0 ' + W + ' ' + H + '" style="aspect-ratio:' + W + '/' + H + ';height:auto">' + g +
    '<line class="sp-cross" x1="0" y1="' + T + '" x2="0" y2="' + (H - B) + '" stroke="#bbb" stroke-dasharray="2 2" style="display:none"/></svg><div class="sp-tip"></div></div>';
  const svg = box.querySelector('svg'), tip = box.querySelector('.sp-tip'), cross = box.querySelector('.sp-cross');
  const allDates = Array.from(new Set([].concat(...fys.map(fy => res.byFy.get(fy).map(p => p[0]))))).sort();
  svg.addEventListener('mousemove', ev => {
    const r = svg.getBoundingClientRect(), mx = (ev.clientX - r.left) / r.width * W;
    if (mx < L || mx > W - R) { tip.style.display = 'none'; cross.style.display = 'none'; return; }
    let bd = allDates[0];
    for (const d of allDates) if (Math.abs(X(d) - mx) < Math.abs(X(bd) - mx)) bd = d;
    cross.setAttribute('x1', X(bd)); cross.setAttribute('x2', X(bd)); cross.style.display = '';
    tip.innerHTML = bd + fys.map((fy, i) => { const v = atOrBefore(res.byFy.get(fy), bd);
      return v == null ? '' : '<br><span style="color:' + CONS_COLORS[i % CONS_COLORS.length] + ';font-weight:700">' + fy + 'E</span> ' + fmtOp(v); }).join('');
    tip.style.display = 'block';
    tip.style.left = Math.max(4, Math.min(X(bd) / W * r.width + 12, r.width - tip.offsetWidth - 4)) + 'px';
    tip.style.top = '4px';
  });
  svg.addEventListener('mouseleave', () => { tip.style.display = 'none'; cross.style.display = 'none'; });
}

// ===== 재무 이력 + 컨센서스 =====
//  o.name · o.annual Map(fy -> [영업이익(천원), 'A'|'E']) · o.quarterly Map(fy*10+q -> 영업이익) · o.cons {fys, byFy} (없으면 추이 생략)
function earnings(el, o) {
  const a = o.annual, q = o.quarterly;
  const head = '<div class="sp-title">' + (o.titleHtml || esc(o.name)) + '<span style="font-weight:500;font-size:12px;color:#888">재무 이력 · 컨센서스</span></div>';
  if (!a || !a.size) { el.innerHTML = head + '<div class="sp-empty">영업이익 데이터가 없습니다</div>'; return; }
  const fys = Array.from(a.keys()).sort((x, y) => x - y);
  let rows = '';
  for (const fy of fys) {
    if (fy < 2020) continue;
    const cur = a.get(fy), prev = a.get(fy - 1);
    const [gv, cls] = growthCell(cur[0], prev ? prev[0] : null), est = cur[1] === 'E';
    rows += '<tr class="yrow" data-fy="' + fy + '"><td class="yr">' + fy + (est ? '<span class="e">E</span>' : '') + '</td>' +
      '<td class="op">' + Math.round(cur[0] / 1e5).toLocaleString() + '<span class="unit">억</span></td>' +
      '<td class="gv ' + cls + '">' + gv + '</td><td class="chev">&#9656; 분기</td></tr>';
  }
  const hasCons = o.cons && o.cons.fys && o.cons.fys.length;
  el.innerHTML = head +
    '<div class="sp-sub">영업이익(억원) · 증가율은 전년 대비 · E = 컨센서스 · 연도를 누르면 분기 실적</div>' +
    '<div class="sp-cols"><div><table class="sp-earn">' + rows + '</table></div>' +
    '<div>' + (hasCons ? '<div class="sp-cons"></div><div class="sp-sub" style="margin-top:4px">연간 영업이익 컨센서스 추이 · 괄호는 첫 관측일 대비 변화</div>'
      : '<div class="sp-empty">컨센서스 추이가 없습니다 (애널리스트 커버리지 없음)</div>') + '</div></div>';
  if (hasCons) { const box = el.querySelector('.sp-cons'); consChart(box, o.cons, box.clientWidth || 0); }
  el.querySelector('.sp-earn').addEventListener('click', ev => {
    const tr = ev.target.closest('tr.yrow');
    if (!tr) return;
    let nxt = tr.nextElementSibling, removed = false;
    while (nxt && nxt.classList.contains('qrow')) { const t = nxt; nxt = nxt.nextElementSibling; t.remove(); removed = true; }
    tr.classList.toggle('on', !removed);
    if (removed) return;
    const fy = Number(tr.dataset.fy);
    let h = '';
    for (let k = 1; k <= 4; k++) {
      const cur = q ? q.get(fy * 10 + k) : null;
      if (cur == null) continue;
      const [gv, cls] = growthCell(cur, q.get((fy - 1) * 10 + k));
      h += '<tr class="qrow"><td class="yr">' + k + 'Q</td><td class="op">' + Math.round(cur / 1e5).toLocaleString() + '<span class="unit">억</span></td>' +
        '<td class="gv ' + cls + '">' + gv + '</td><td class="chev">' + (k === 1 ? 'YoY' : '') + '</td></tr>';
    }
    tr.insertAdjacentHTML('afterend', h || '<tr class="qrow"><td class="yr" colspan="4" style="color:#aaa">분기 실적 데이터가 없습니다</td></tr>');
  });
}

window.StockPanels = { line: line, earnings: earnings };
})();
