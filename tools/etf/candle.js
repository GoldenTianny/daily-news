// 캔들 차트 공용 모듈 — ETF 검색기 종목 화면(index.html)과 미너비니 템플릿 차트 모아보기(minervini.html)가 함께 씀
// 일봉 캔들 + 이동평균(5·20·60·120일) + 자동 지지·저항 추세선. 거래량 자료가 없어 거래량 패널은 없음.
// 사용: CandleChart.draw(el, { name, price, ohlc, pre, width, minWidth, height, titleHtml, titleText, note, save })
(function () {
'use strict';
const CANDLE_PAD = 12;           // 추세선 연장용 오른쪽 여백(거래일)
const PIVOT_K = 5;               // 앞뒤 5거래일 중 최고·최저면 고점·저점(피벗)
const TL_TOL = 0.01;             // 추세선 판정 허용 오차 (종가 기준 1%)
const TL_MIN_GAP = 10;           // 추세선을 잇는 두 피벗의 최소 간격(거래일)
const TL_FAR = 0.2;              // 현재가보다 20% 넘게 위에 있는 저항선, 40% 넘게 아래에 있는 지지선은 제외
const BRK_RECENT = 60;           // 돌파한 선은 최근 60거래일 안에 돌파한 것만
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const css = document.createElement('style');
css.textContent =
  '.cc-title{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;font-weight:600;font-size:15px}' +
  '.cc-sub{font-size:12px;color:#999;margin:2px 0 8px}' +
  '.cc-legend{display:flex;flex-wrap:wrap;gap:3px 12px;color:#555}' +
  '.cc-item{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}' +
  '.cc-item i{display:inline-block;width:16px;height:0}' +
  '.cc-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}' +
  '.cc-wrap{position:relative}.cc-wrap svg{display:block;width:100%}' +
  '.cc-save{margin-left:auto;padding:3px 10px;border-radius:999px;border:1px solid #c5cae9;background:#fff;color:#3f51b5;' +
    'font:inherit;font-size:11.5px;font-weight:600;cursor:pointer;white-space:nowrap}' +
  '.cc-save:hover{background:#e8eaf6}.cc-save:disabled{opacity:.5;cursor:default}' +
  '.cc-tip{position:absolute;pointer-events:none;display:none;z-index:10;background:rgba(26,35,126,.94);color:#fff;' +
    'font-size:12px;padding:6px 10px;border-radius:6px;white-space:nowrap;line-height:1.5;text-align:left}';
document.head.appendChild(css);

// 고점·저점(피벗) 찾기: 앞뒤 PIVOT_K 거래일 안에서 가장 높은 고가 / 가장 낮은 저가
function findPivots(bars) {
  const hi = [], lo = [];
  for (let i = PIVOT_K; i < bars.length - PIVOT_K; i++) {
    let isH = true, isL = true;
    for (let k = i - PIVOT_K; k <= i + PIVOT_K; k++) {
      if (k === i) continue;
      if (bars[k].h > bars[i].h || (bars[k].h === bars[i].h && k < i)) isH = false;
      if (bars[k].l < bars[i].l || (bars[k].l === bars[i].l && k < i)) isL = false;
    }
    if (isH) hi.push(i);
    if (isL) lo.push(i);
  }
  return { hi: hi, lo: lo };
}

// 추세선 고르기
//  지지: 저점 두 개를 이은 오르는 선 중, 그 뒤로 종가가 한 번도 선 아래로 내려가지 않은 가장 긴 선
//  저항: 고점 두 개를 이은 선 중, 그 뒤로 종가가 한 번도 선 위로 올라가지 않은 가장 긴 선
//  돌파한 선: 고점 두 개를 이은 내려가는 선 중, 두 번째 고점 뒤 최근 60거래일 안에 종가가 선을 넘어선 가장 긴 선 (+ 돌파일)
//  현재가에서 너무 먼 선(저항 +20% 초과, 지지 −40% 초과)은 제외
function findTrendlines(bars) {
  const n = bars.length, pv = findPivots(bars);
  const mk = (i, j, key) => {
    const m = (bars[j][key] - bars[i][key]) / (j - i);
    return { i: i, j: j, m: m, at: x => bars[i][key] + m * (x - i) };
  };
  let sup = null, res = null, brk = null;
  const lastC = bars[n - 1].c;
  for (let a = 0; a < pv.lo.length; a++) for (let b = a + 1; b < pv.lo.length; b++) {
    const i = pv.lo[a], j = pv.lo[b];
    if (j - i < TL_MIN_GAP) continue;
    const ln = mk(i, j, 'l');
    if (ln.m <= 0) continue;
    let ok = true;
    for (let x = i; x < n && ok; x++) if (bars[x].c < ln.at(x) * (1 - TL_TOL)) ok = false;
    if (ok && ln.at(n - 1) >= lastC * (1 - TL_FAR * 2) && (!sup || j - i > sup.j - sup.i)) sup = ln;
  }
  for (let a = 0; a < pv.hi.length; a++) for (let b = a + 1; b < pv.hi.length; b++) {
    const i = pv.hi[a], j = pv.hi[b];
    if (j - i < TL_MIN_GAP) continue;
    const ln = mk(i, j, 'h');
    let ok = true;
    for (let x = i; x <= j && ok; x++) if (bars[x].c > ln.at(x) * (1 + TL_TOL)) ok = false;
    if (!ok) continue;
    let bx = -1;
    for (let x = j + 1; x < n; x++) if (bars[x].c > ln.at(x) * (1 + TL_TOL)) { bx = x; break; }
    if (bx < 0) { if (ln.at(n - 1) <= lastC * (1 + TL_FAR) && (!res || j - i > res.j - res.i)) res = ln; }
    else if (ln.m < 0 && bx >= n - BRK_RECENT && (!brk || j - i > brk.j - brk.i)) { ln.bx = bx; brk = ln; }
  }
  return { sup: sup, res: res, brk: brk };
}

// el 안에 캔들 차트를 그린다.
//  o.name 종목명 · o.price [[날짜, 종가]...] (그릴 구간, 오름차순) · o.ohlc Map(날짜 -> [시가, 고가, 저가])
//  o.pre 그 이전 종가 배열(이동평균용, 없어도 됨) · o.width 그림 너비(px, 없으면 el 너비) · o.height 그림 높이(px)
//  o.minWidth 그림 최소 너비 — 화면이 이보다 좁으면 차트를 가로로 밀어 보게 하고 최근 쪽(오른쪽 끝)부터 보여줌
//  o.titleHtml 제목 왼쪽 HTML(없으면 종목명) · o.titleText 저장 이미지에 넣을 제목(일반 글자) · o.note false 면 하단 안내문 생략
//  o.save false 면 '이미지 저장' 버튼 생략 · o.tip false 면 누르거나 올렸을 때 시가·고가·저가·종가 말풍선을 띄우지 않음
function draw(el, o) {
  const name = o.name, price = o.price, ohlc = o.ohlc || new Map(), pre = o.pre;
  // 이동평균은 (1년 이전 종가 + 1년치 종가) 전체로 계산한 뒤 화면 구간만 잘라 씀
  const np = pre ? pre.length : 0;
  const closes = (pre || []).concat(price.map(p => p[1]));
  const sma = w => { const out = new Array(closes.length).fill(null); let sum = 0;
    for (let i = 0; i < closes.length; i++) { sum += closes[i]; if (i >= w) sum -= closes[i - w]; if (i >= w - 1) out[i] = sum / w; }
    return out.slice(np); };
  const MAS = [[5, '#7e57c2'], [20, '#f59e0b'], [60, '#26a69a'], [120, '#8d8d8d']];
  const maAll = MAS.map(([w]) => sma(w));
  const start = 0;
  const bars = [];
  for (let i = 0; i < price.length; i++) {
    const [d, c] = price[i], q = ohlc.get(d);
    const op = q ? q[0] : c;
    bars.push({ d: d, o: op, c: c, h: Math.max(q ? q[1] : c, op, c), l: Math.min(q ? q[2] : c, op, c),
      prev: i > 0 ? price[i - 1][1] : (pre && pre.length ? pre[pre.length - 1] : null) });
  }
  const n = bars.length, tl = findTrendlines(bars);

  const avail = Math.max(300, o.width || el.clientWidth);
  const W = Math.max(avail, o.minWidth || 0);
  const H = o.height || 340, L = 10, R = 64, T = 14, B = 26;
  const step = (W - L - R) / (n + CANDLE_PAD);
  const X = i => L + (i + 0.5) * step;
  let vmin = Infinity, vmax = -Infinity;
  for (const b of bars) { if (b.l < vmin) vmin = b.l; if (b.h > vmax) vmax = b.h; }
  maAll.forEach(a => { for (let i = start; i < a.length; i++) if (a[i] != null) { if (a[i] < vmin) vmin = a[i]; if (a[i] > vmax) vmax = a[i]; } });
  const pad = (vmax - vmin) * 0.06 || vmax * 0.05;
  vmin -= pad; vmax += pad;
  const Y = v => T + (vmax - v) / (vmax - vmin) * (H - B - T);
  const fmt = v => Math.round(v).toLocaleString();
  const UP = '#e53935', DN = '#1e63d6';

  // 그리드: 보기 좋은 간격의 가격 눈금(우측) + 월 경계
  let g = '';
  const raw = (vmax - vmin) / 5, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const tick = [1, 2, 2.5, 5, 10].map(k => k * mag).find(t => t >= raw) || raw;
  for (let v = Math.ceil(vmin / tick) * tick; v <= vmax; v += tick) {
    const y = Y(v).toFixed(1);
    g += '<line x1="' + L + '" y1="' + y + '" x2="' + (W - R) + '" y2="' + y + '" stroke="#eee"/>' +
      '<text x="' + (W - R + 6) + '" y="' + y + '" dominant-baseline="middle" font-size="11" fill="#888">' + fmt(v) + '</text>';
  }
  let lastLbl = -99;
  for (let i = 1; i < n; i++) {
    if (bars[i].d.slice(0, 7) === bars[i - 1].d.slice(0, 7)) continue;
    const xv = X(i) - step / 2, x = xv.toFixed(1);
    g += '<line x1="' + x + '" y1="' + T + '" x2="' + x + '" y2="' + (H - B) + '" stroke="#f1f1f1"/>';
    if (xv - lastLbl < 44) continue;        // 좁은 화면에서는 월 라벨을 건너뛰어 겹치지 않게
    lastLbl = xv;
    g += '<text x="' + x + '" y="' + (H - 8) + '" font-size="11" fill="#888">' + bars[i].d.slice(2, 7).replace('-', '.') + '</text>';
  }

  // 이동평균선
  let ma = '';
  MAS.forEach(([w, col], k) => {
    let d = '';
    for (let i = 0; i < n; i++) { const v = maAll[k][start + i]; if (v == null) continue; d += (d ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); }
    if (d) ma += '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.3"/>';
  });

  // 캔들 (오르면 빨강, 내리면 파랑)
  let cd = '';
  const bw = Math.max(1.5, Math.min(12, step * 0.76)), wick = step >= 4 ? 1.3 : 1;
  for (let i = 0; i < n; i++) {
    const b = bars[i], col = b.c >= b.o ? UP : DN, x = X(i);
    const y1 = Y(Math.max(b.o, b.c)), y2 = Y(Math.min(b.o, b.c));
    cd += '<line x1="' + x.toFixed(1) + '" y1="' + Y(b.h).toFixed(1) + '" x2="' + x.toFixed(1) + '" y2="' + Y(b.l).toFixed(1) + '" stroke="' + col + '" stroke-width="' + wick + '"/>' +
      '<rect x="' + (x - bw / 2).toFixed(1) + '" y="' + y1.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + Math.max(1, y2 - y1).toFixed(1) + '" fill="' + col + '"/>';
  }

  // 추세선: 오른쪽 여백 끝까지 연장하되 가격 범위를 벗어나면 거기서 자름
  const seg = (ln, col, dash, wd) => {
    let xe = n - 1 + CANDLE_PAD;
    while (xe > ln.j && (ln.at(xe) > vmax || ln.at(xe) < vmin)) xe -= 0.5;
    return '<line x1="' + X(ln.i).toFixed(1) + '" y1="' + Y(ln.at(ln.i)).toFixed(1) + '" x2="' + X(xe).toFixed(1) + '" y2="' + Y(ln.at(xe)).toFixed(1) +
      '" stroke="' + col + '" stroke-width="' + wd + '"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + ' stroke-linecap="round"/>';
  };
  let tls = '';
  if (tl.brk) {
    const bx = tl.brk.bx, y = Y(bars[bx].l) + 6;
    tls += seg(tl.brk, '#d946a8', '2 4', 1.6) +
      '<path d="M' + X(bx).toFixed(1) + ' ' + y.toFixed(1) + 'l-5 9h10z" fill="#e53935"/>';
  }
  if (tl.res) tls += seg(tl.res, '#e0489e', '', 2);
  if (tl.sup) tls += seg(tl.sup, '#12a5c4', '', 2.2);

  // 현재가 표시선 + 우측 가격표
  const lastB = bars[n - 1], chg = lastB.prev ? lastB.c / lastB.prev - 1 : null;
  const ccol = chg == null || chg === 0 ? '#666' : chg > 0 ? UP : DN, yl = Y(lastB.c);
  const cur = '<line x1="' + L + '" y1="' + yl.toFixed(1) + '" x2="' + (W - R) + '" y2="' + yl.toFixed(1) + '" stroke="' + ccol + '" stroke-dasharray="1 3"/>' +
    '<rect x="' + (W - R + 2) + '" y="' + (yl - 9).toFixed(1) + '" width="' + (R - 4) + '" height="18" rx="3" fill="' + ccol + '"/>' +
    '<text x="' + (W - R / 2) + '" y="' + yl.toFixed(1) + '" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="700" fill="#fff">' + fmt(lastB.c) + '</text>';

  // 범례 항목 [색, 글자, 점선 여부] — 화면과 저장 이미지가 같이 씀
  const items = MAS.map(([w, col]) => [col, w + '일', false]);
  if (tl.sup) items.push(['#12a5c4', '지지 추세선', false]);
  if (tl.res) items.push(['#e0489e', '저항 추세선', false]);
  if (tl.brk) items.push(['#d946a8', '▲ 돌파일(돌파한 선 · ' + bars[tl.brk.bx].d.slice(5).replace('-', '/') + ')', true]);
  const legend = items.map(([col, txt, dash]) => '<span class="cc-item"><i style="border-top:2px ' + (dash ? 'dotted' : 'solid') + ' ' + col + '"></i>' +
    esc(txt).replace('▲', '<span style="color:#e53935">&#9650;</span>') + '</span>').join('');
  const priceText = fmt(lastB.c) + (chg == null ? '' : '  ' + (chg > 0 ? '+' : '') + (chg * 100).toFixed(2) + '%') + '  (' + lastB.d + ')';
  const chartSvg = g + ma + cd + tls + cur;

  el.innerHTML =
    '<div class="cc-title">' + (o.titleHtml || '&#128201; ' + esc(name) + ' &middot; 최근 ' + price.length + '거래일') +
      '<span style="margin-left:auto;font-weight:600;color:' + ccol + '">' + fmt(lastB.c) +
      (chg == null ? '' : ' &nbsp;' + (chg > 0 ? '+' : '') + (chg * 100).toFixed(2) + '%') +
      ' <span style="font-weight:400;font-size:12px">(' + lastB.d + ')</span></span></div>' +
    '<div class="cc-sub cc-legend">' + legend +
      (o.save === false ? '' : '<button type="button" class="cc-save" title="이 차트를 이미지(PNG)로 저장">&#128247; 이미지 저장</button>') + '</div>' +
    '<div class="cc-scroll"><div class="cc-wrap"' + (W > avail ? ' style="width:' + W + 'px"' : '') + '><svg viewBox="0 0 ' + W + ' ' + H + '" style="aspect-ratio:' + W + '/' + H + ';height:auto">' + chartSvg +
    '<line class="cc-cross" x1="0" y1="' + T + '" x2="0" y2="' + (H - B) + '" stroke="#bbb" stroke-dasharray="2 2" style="display:none"/>' +
    '</svg><div class="cc-tip"></div></div></div>' +
    (o.note === false ? '' : '<div class="cc-sub" style="margin:6px 0 0">추세선은 앞뒤 ' + PIVOT_K + '거래일 기준 고점·저점을 이어 자동으로 그린 참고선입니다. 거래량은 자료가 없어 표시하지 않습니다.</div>');

  // 호버: 그날의 시가·고가·저가·종가
  const wrap = el.querySelector('.cc-wrap'), svg = wrap.querySelector('svg');
  const tip = wrap.querySelector('.cc-tip'), cross = svg.querySelector('.cc-cross');
  const show = clientX => {
    const r = svg.getBoundingClientRect();
    const i = Math.floor(((clientX - r.left) / r.width * W - L) / step);
    if (i < 0 || i >= n) { tip.style.display = 'none'; cross.style.display = 'none'; return; }
    const b = bars[i], ch = b.prev ? b.c / b.prev - 1 : null;
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.style.display = '';
    tip.innerHTML = b.d + '<br>시가 ' + fmt(b.o) + ' · 고가 ' + fmt(b.h) + '<br>저가 ' + fmt(b.l) + ' · 종가 ' + fmt(b.c) +
      (ch == null ? '' : ' (' + (ch > 0 ? '+' : '') + (ch * 100).toFixed(2) + '%)');
    tip.style.display = 'block';
    const px = X(i) / W * r.width;
    tip.style.left = Math.max(4, Math.min(px + 12, r.width - tip.offsetWidth - 4)) + 'px';
    tip.style.top = '4px'; tip.style.bottom = 'auto';
  };
  if (o.tip !== false) {
    svg.addEventListener('mousemove', ev => show(ev.clientX));
    svg.addEventListener('touchstart', ev => show(ev.touches[0].clientX), { passive: true });
    svg.addEventListener('touchmove', ev => show(ev.touches[0].clientX), { passive: true });
    svg.addEventListener('mouseleave', () => { tip.style.display = 'none'; cross.style.display = 'none'; });
  }
  if (W > avail) { const sc = el.querySelector('.cc-scroll'); sc.scrollLeft = sc.scrollWidth; }   // 최근 쪽부터

  // 이 차트를 PNG 로 만드는 함수 — 개별 저장 버튼과 일괄 저장(CandleChart.png)이 같이 씀
  const cfg = { W: W, H: H, chart: chartSvg, items: items, title: o.titleText || name, priceText: priceText, priceCol: ccol,
    file: name.replace(/[\\/:*?"<>|\s]+/g, '_') + '_' + lastB.d + '.png' };
  el.__ccPng = () => renderPng(cfg).then(blob => ({ blob: blob, name: cfg.file }));
  const btn = el.querySelector('.cc-save');
  if (btn) btn.addEventListener('click', () => {
    btn.disabled = true;
    el.__ccPng().then(f => deliver([f]))
      .catch(e => alert('이미지를 저장하지 못했습니다: ' + e.message))
      .then(() => { btn.disabled = false; });
  });
}

// 차트 한 장을 PNG(Blob)로: 제목 · 현재가 · 범례를 얹은 SVG 를 만들어 캔버스에 2배 해상도로 그린다
function renderPng(c) {
  const HEAD = 58, FOOT = 6, W = c.W, H = c.H + HEAD + FOOT;
  const font = "-apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic','Apple SD Gothic Neo',sans-serif";
  const meas = document.createElement('canvas').getContext('2d');
  meas.font = '12px ' + font;
  let lx = 12, lgd = '';
  for (const [col, txt, dash] of c.items) {
    lgd += '<line x1="' + lx + '" y1="44" x2="' + (lx + 16) + '" y2="44" stroke="' + col + '" stroke-width="2"' + (dash ? ' stroke-dasharray="2 3"' : '') + '/>' +
      '<text x="' + (lx + 21) + '" y="48" font-size="12" fill="#555">' + esc(txt) + '</text>';
    lx += 21 + meas.measureText(txt).width + 14;
  }
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" font-family="' + font + '">' +
    '<rect width="' + W + '" height="' + H + '" fill="#fff"/>' +
    '<text x="12" y="24" font-size="16" font-weight="700" fill="#1a237e">' + esc(c.title) + '</text>' +
    '<text x="' + (W - 12) + '" y="24" text-anchor="end" font-size="14" font-weight="700" fill="' + c.priceCol + '">' + esc(c.priceText) + '</text>' +
    lgd + '<text x="' + (W - 12) + '" y="48" text-anchor="end" font-size="11" fill="#b0b6c8">gjbuffet.kr</text>' +
    '<g transform="translate(0,' + HEAD + ')">' + c.chart + '</g></svg>';
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onerror = () => reject(new Error('차트 그림을 읽지 못했습니다'));
    img.onload = () => {
      const k = 2, cv = document.createElement('canvas');
      cv.width = W * k; cv.height = H * k;
      cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
      cv.toBlob(blob => { if (blob) resolve(blob); else reject(new Error('PNG 변환 실패')); }, 'image/png');
    };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  });
}

// 만든 PNG 들을 사용자에게 넘김: 휴대폰은 공유 창 한 번(사진에 저장 포함), 그 외에는 파일로 차례차례 내려받기
// files: [{blob, name}]. 공유 창을 사용자가 닫은 것은 오류로 보지 않는다. 브라우저가 공유를 막으면(NotAllowedError) 그대로 던진다
function deliver(files) {
  const touch = window.matchMedia && matchMedia('(pointer: coarse)').matches;
  if (touch && typeof File === 'function' && navigator.canShare) {
    const fs = files.map(f => new File([f.blob], f.name, { type: 'image/png' }));
    if (navigator.canShare({ files: fs })) {
      return navigator.share({ files: fs }).catch(e => { if (e && e.name === 'NotAllowedError') throw e; });
    }
  }
  return files.reduce((p, f, i) => p.then(() => new Promise(done => {
    const a = document.createElement('a'), url = URL.createObjectURL(f.blob);
    a.href = url; a.download = f.name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    setTimeout(done, i < files.length - 1 ? 350 : 0);       // 연속 다운로드가 막히지 않게 간격을 둠
  })), Promise.resolve());
}

// png(el): draw 로 그린 컨테이너의 차트를 {blob, name} 으로 · deliver(files): 여러 장을 한 번에 저장
window.CandleChart = { draw: draw, png: el => el.__ccPng ? el.__ccPng() : Promise.reject(new Error('차트가 아직 그려지지 않았습니다')), deliver: deliver };
})();
