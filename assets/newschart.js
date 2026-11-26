// 일일브리프 기사 하단 '종목 차트' — 기사에 나온 종목 버튼을 누르면 그 자리에서 캔들 차트를 펼친다.
// 기본으로 기사마다 첫 종목 차트가 펼쳐져 있고, 다른 버튼을 누르면 바꿔 보거나 같은 버튼을 다시 눌러 접는다.
// 블록: <div class="stock-charts" data-stocks='[{"name":"삼성SDI","code":"A006400"}]'></div>  (tools/news_stock_charts.py 가 삽입)
// 자료: /db/newschart/<code>.json (최근 150거래일 종가·시고저 + 120일선용 앞쪽 종가). 그리기: /tools/etf/candle.js
(function () {
'use strict';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const css = document.createElement('style');
css.textContent =
  '.stock-charts{margin:14px 0 4px;padding:12px 12px 10px;border:1px solid #e3e8f2;border-radius:12px;background:#f8faff}' +
  '.sc-head{font-size:12.5px;font-weight:700;color:#1a3a6c;margin-bottom:8px}' +
  '.sc-chips{display:flex;flex-wrap:wrap;gap:6px}' +
  '.sc-chip{padding:6px 12px;border-radius:999px;border:1px solid #c5cae9;background:#fff;color:#1a3a6c;' +
    'font:inherit;font-size:13px;font-weight:600;cursor:pointer;line-height:1.2}' +
  '.sc-chip:hover{background:#eef1fb}.sc-chip.on{background:#1a3a6c;border-color:#1a3a6c;color:#fff}' +
  '.sc-panel{margin-top:10px;background:#fff;border-radius:10px;padding:10px 8px 8px;border:1px solid #eef1f6}' +
  '.sc-panel[hidden]{display:none}' +
  '.sc-msg{padding:28px 6px;text-align:center;color:#999;font-size:13px}' +
  '.sc-more{display:inline-block;margin-top:8px;font-size:12.5px;font-weight:600;color:#3f51b5;text-decoration:none}' +
  '.sc-more:hover{text-decoration:underline}.sc-asof{font-size:11.5px;color:#999;margin-left:6px}';
document.head.appendChild(css);

let candleP = null;
function loadCandle() {
  if (window.CandleChart) return Promise.resolve();
  if (!candleP) candleP = new Promise((ok, ng) => {
    const s = document.createElement('script');
    s.src = '/tools/etf/candle.js'; s.onload = ok; s.onerror = () => { candleP = null; ng(new Error('candle')); };
    document.head.appendChild(s);
  });
  return candleP;
}
const cache = new Map();
function loadData(code) {
  if (!cache.has(code)) cache.set(code, fetch('/db/newschart/' + code + '.json', { cache: 'no-cache' })
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .catch(e => { cache.delete(code); throw e; }));
  return cache.get(code);
}

function show(panel, st) {
  panel.hidden = false;
  panel.innerHTML = '<div class="sc-msg">차트를 불러오는 중…</div>';
  const tok = panel.__tok = (panel.__tok || 0) + 1;
  Promise.all([loadCandle(), loadData(st.code)]).then(([, d]) => {
    if (tok !== panel.__tok) return;
    panel.innerHTML = '<div class="sc-chart"></div><a class="sc-more" href="/tools/etf/?stock=' +
      encodeURIComponent(d.name) + '">🔎 목표주가·실적 등 종목 상세 보기 →</a><span class="sc-asof">' +
      esc(d.asof.replace(/-/g, '.')) + ' 종가 기준</span>';
    const box = panel.firstChild;
    CandleChart.draw(box, { name: d.name, price: d.price, ohlc: new Map(Object.entries(d.ohlc)), pre: d.pre,
      width: Math.max(300, panel.clientWidth - 16), height: 300, save: false });
  }).catch(() => {
    if (tok !== panel.__tok) return;
    panel.innerHTML = '<div class="sc-msg">차트를 불러오지 못했습니다. <a class="sc-more" href="/tools/etf/?stock=' +
      encodeURIComponent(st.name) + '">종목 화면에서 보기 →</a></div>';
  });
}

function init(el) {
  let list;
  try { list = JSON.parse(el.dataset.stocks || '[]'); } catch (e) { return; }
  if (!list.length) return;
  el.innerHTML = '<div class="sc-head">📈 기사 속 종목 차트</div><div class="sc-chips">' +
    list.map((s, i) => '<button type="button" class="sc-chip" data-i="' + i + '">' + esc(s.name) + '</button>').join('') +
    '</div><div class="sc-panel" hidden></div>';
  const panel = el.querySelector('.sc-panel');
  el.querySelector('.sc-chips').addEventListener('click', ev => {
    const b = ev.target.closest('.sc-chip');
    if (!b) return;
    const on = b.classList.contains('on');
    el.querySelectorAll('.sc-chip').forEach(x => x.classList.remove('on'));
    if (on) { panel.hidden = true; panel.__tok = (panel.__tok || 0) + 1; return; }
    b.classList.add('on');
    show(panel, list[+b.dataset.i]);
    if (window.gtag) gtag('event', 'news_stock_chart', { stock: list[+b.dataset.i].name });
  });
  // 기본: 첫 종목 차트를 펼친 상태 — 화면 가까이 왔을 때 그려서 처음 로딩을 가볍게
  const first = el.querySelector('.sc-chip');
  first.classList.add('on');
  panel.hidden = false;
  panel.innerHTML = '<div class="sc-msg">차트를 불러오는 중…</div>';
  const open = () => { if (first.classList.contains('on') && !panel.__tok) show(panel, list[0]); };
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { io.disconnect(); open(); } }, { rootMargin: '400px 0px' });
    io.observe(el);
  } else open();
}

function run() { document.querySelectorAll('.stock-charts').forEach(init); }
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
