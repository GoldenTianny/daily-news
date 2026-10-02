/* 매매 복기 — 체결내역 파싱 · 거래 단위 손익 분석 · 차트
 * 체결내역은 두 곳 중 최신 것을 씁니다. 둘 다 마스터 본인만 열 수 있습니다.
 *   1) admin/data/journal.enc.json — 공개키로 잠근 암호문 (admin/journal-encrypt.mjs 로 생성).
 *      푸는 개인키는 Supabase journal_secret (supabase/003_journal_secret.sql) 에만 있음.
 *   2) Supabase trade_journal — 이 화면에서 직접 올린 원문 (supabase/002_trade_journal.sql). */
(function (root) {
'use strict';

var OWNER_EMAIL = 'tyannytyanny@gmail.com';
var ENC_URL = '/admin/data/journal.enc.json';
var CHART_SRC = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js';
var ETF_PREFIX = ['ACE', 'KODEX', 'TIGER', 'PLUS', 'SOL', 'TIME', 'TIMEFOLIO', 'HANARO', 'KIWOOM', 'RISE', 'KOSEF', 'ARIRANG', 'HANA', 'WON', '1Q', 'BNK', 'FOCUS', 'TREX', 'UNICORN', 'KoAct', 'VITA', 'DAISHIN343', 'ITF', 'MASTER', 'KBSTAR'];

/* ---------- 파싱 ----------
 * "■ 매수 내역" / "■ 매도 내역" 아래의
 *   2026-01-05 12:53  한미반도체   18   158,800   2,858,400  [비고]
 * 형식 줄을 읽습니다. */
var LINE = /^\s*(\d{4}-\d\d-\d\d)\s+(\d\d:\d\d)\s+(.+?)\s+([\d,]+)\s+([\d,.]+)\s+([\d,]+)\s*(.*?)\s*$/;
var num = function (s) { return Number(String(s).replace(/,/g, '')); };

function parse(text) {
  var side = null, rows = [];
  String(text || '').split(/\r?\n/).forEach(function (l) {
    if (/■\s*매수\s*내역/.test(l)) { side = 'B'; return; }
    if (/■\s*매도\s*내역/.test(l)) { side = 'S'; return; }
    if (/^\s*■/.test(l)) { side = null; return; }
    if (!side) return;
    var m = LINE.exec(l);
    if (!m) return;
    rows.push({ side: side, date: m[1], time: m[2], name: m[3].trim(), qty: num(m[4]), price: num(m[5]), amt: num(m[6]), note: m[7] });
  });
  rows.sort(function (a, b) {
    return a.date < b.date ? -1 : a.date > b.date ? 1 : a.time < b.time ? -1 : a.time > b.time ? 1 : (a.side === 'B' ? -1 : 1) - (b.side === 'B' ? -1 : 1);
  });
  return rows;
}

/* ---------- 분석 ----------
 * 평균단가 방식. 한 종목을 0주에서 사기 시작해 다시 0주가 될 때까지가 "거래 1회". */
var DAY = 86400000;
var dnum = function (s) { return Date.parse(s + 'T00:00:00Z') / DAY; };
var isEtf = function (n) { return ETF_PREFIX.some(function (p) { return n.indexOf(p + ' ') === 0; }); };
var sum = function (a, f) { return a.reduce(function (s, x) { return s + f(x); }, 0); };
var median = function (a) { if (!a.length) return 0; var s = a.slice().sort(function (x, y) { return x - y; }), h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; };
var mean = function (a) { return a.length ? sum(a, function (x) { return x; }) / a.length : 0; };

function analyze(rows) {
  var pos = {}, cycles = [], sells = [], orphan = [], splits = [];
  rows.forEach(function (r) {
    var p = pos[r.name] || (pos[r.name] = { q: 0, cost: 0, cyc: null, last: null });
    // 무상증자·액면분할 추정: 보유 중 15일 안에 가격이 1/2 이하로 뚝 떨어진 매도 → 그 배수만큼 수량 보정
    if (r.side === 'S' && p.q > 0 && p.last && dnum(r.date) - dnum(p.last.date) <= 15) {
      var ratio = r.price / p.last.price;
      if (ratio > 0.25 && ratio < 0.62) {
        var f = Math.round(p.last.price / r.price);
        if (f >= 2 && Math.abs(p.last.price / r.price - f) < 0.25) { p.q *= f; splits.push({ name: r.name, date: r.date, factor: f }); }
      }
    }
    p.last = r;
    if (r.side === 'B') {
      var avgBefore = p.q > 0 ? p.cost / p.q : null;
      if (p.q === 0) p.cyc = { name: r.name, start: r.date, buys: [], sells: [], pnl: 0, buycost: 0, maxcost: 0 };
      p.q += r.qty; p.cost += r.amt;
      var c = p.cyc;
      c.buys.push({ date: r.date, time: r.time, qty: r.qty, price: r.price, avgBefore: avgBefore });
      c.buycost += r.amt; c.maxcost = Math.max(c.maxcost, p.cost);
      return;
    }
    var q = r.qty;
    if (p.q === 0) { orphan.push(r); return; }
    if (q > p.q) { orphan.push(Object.assign({}, r, { qty: q - p.q })); q = p.q; }
    var avg = p.cost / p.q, pnl = (r.price - avg) * q;
    p.cost -= avg * q; p.q -= q;
    var s = { date: r.date, time: r.time, name: r.name, qty: q, price: r.price, avg: avg, pnl: pnl, ret: r.price / avg - 1 };
    p.cyc.sells.push(s); p.cyc.pnl += pnl; sells.push(s);
    if (p.q === 0) { p.cyc.end = r.date; cycles.push(p.cyc); p.cost = 0; }
  });

  cycles.forEach(function (c) {
    c.ret = c.pnl / c.buycost;
    c.days = dnum(c.end) - dnum(c.start);
    c.avgdown = c.buys.filter(function (b) { return b.avgBefore && b.price < b.avgBefore * 0.99; }).length;
    c.pyramid = c.buys.filter(function (b) { return b.avgBefore && b.price > b.avgBefore * 1.01; }).length;
    c.stair = c.pnl < 0 && c.sells.length >= 2 && c.sells[c.sells.length - 1].ret < c.sells[0].ret - 0.02;
  });

  var W = cycles.filter(function (c) { return c.pnl > 0; }), L = cycles.filter(function (c) { return c.pnl <= 0; });
  var pnlOf = function (c) { return c.pnl; };
  var grp = function (label, g) { return { label: label, n: g.length, win: g.filter(function (c) { return c.pnl > 0; }).length, pnl: sum(g, pnlOf) }; };

  // 날짜·월별 실현손익 (매도 시점 기준, 아직 안 끝난 거래의 부분 매도 포함)
  var byDay = {};
  sells.forEach(function (s) { byDay[s.date] = (byDay[s.date] || 0) + s.pnl; });
  var days = Object.keys(byDay).sort(), cum = 0;
  var cumSeries = days.map(function (d) { cum += byDay[d]; return [d, cum]; });
  var byMonth = {};
  days.forEach(function (d) { var m = d.slice(0, 7); byMonth[m] = (byMonth[m] || 0) + byDay[d]; });

  var bins = [[-1e9, -15, '-15% 이하'], [-15, -10, '-15~-10%'], [-10, -7, '-10~-7%'], [-7, -5, '-7~-5%'], [-5, -3, '-5~-3%'], [-3, 0, '-3~0%'], [0, 3, '0~3%'], [3, 7, '3~7%'], [7, 15, '7~15%'], [15, 1e9, '15% 이상']];
  var hist = bins.map(function (b) {
    var g = cycles.filter(function (c) { var r = c.ret * 100; return r > b[0] && r <= b[1]; });
    return { label: b[2], n: g.length, pnl: sum(g, pnlOf) };
  });

  var TB = ['장전(~09:00)', '09:00-09:30', '09:30-11:00', '11:00-14:00', '14:00-15:30', '장후·NXT'];
  var tb = TB.map(function () { return []; });
  cycles.forEach(function (c) {
    var t = c.buys[0].time.split(':'), mm = +t[0] * 60 + +t[1];
    tb[mm < 540 ? 0 : mm < 570 ? 1 : mm < 660 ? 2 : mm < 840 ? 3 : mm <= 930 ? 4 : 5].push(c);
  });

  var whatif = [-0.03, -0.05, -0.07, -0.10].map(function (cap) {
    var g = sells.filter(function (s) { return s.ret < cap; });
    return { label: Math.round(cap * 100) + '%', n: g.length, saved: sum(g, function (s) { return (cap - s.ret) * s.avg * s.qty; }) };
  });

  // 전량 매도 후 7일 안에 같은 종목 재매수
  var byName = {};
  cycles.forEach(function (c) { (byName[c.name] = byName[c.name] || []).push(c); });
  var reentry = [];
  Object.keys(byName).forEach(function (n) {
    var cs = byName[n];
    for (var i = 1; i < cs.length; i++) {
      var a = cs[i - 1], b = cs[i];
      if (dnum(b.start) - dnum(a.end) <= 7) reentry.push({ name: n, higher: b.buys[0].price > a.sells[a.sells.length - 1].price, pnl: b.pnl });
    }
  });

  var stair = L.filter(function (c) { return c.stair; });
  var openPos = Object.keys(pos).filter(function (k) { return pos[k].q > 0; }).map(function (k) { return { name: k, qty: pos[k].q, cost: pos[k].cost }; });
  var etfC = cycles.filter(function (c) { return isEtf(c.name); }), stkC = cycles.filter(function (c) { return !isEtf(c.name); });

  return {
    rows: rows, cycles: cycles, sells: sells, orphan: orphan, splits: splits, openPos: openPos,
    period: rows.length ? [rows[0].date, rows[rows.length - 1].date] : ['', ''],
    nBuy: rows.filter(function (r) { return r.side === 'B'; }).length,
    nSell: rows.filter(function (r) { return r.side === 'S'; }).length,
    realized: sum(sells, function (s) { return s.pnl; }),
    win: W.length, loss: L.length,
    gw: sum(W, pnlOf), gl: sum(L, pnlOf),
    avgWin: mean(W.map(function (c) { return c.ret; })), avgLoss: mean(L.map(function (c) { return c.ret; })),
    medDaysWin: median(W.map(function (c) { return c.days; })), medDaysLoss: median(L.map(function (c) { return c.days; })),
    big: cycles.filter(function (c) { return c.ret > 0.15; }).length,
    firstSellLoss: median(L.map(function (c) { return c.sells[0].ret; })),
    worstSellLoss: median(L.map(function (c) { return Math.min.apply(null, c.sells.map(function (s) { return s.ret; })); })),
    cumSeries: cumSeries,
    monthly: Object.keys(byMonth).sort().map(function (m) { return [m, byMonth[m]]; }),
    worstDays: days.map(function (d) { return [d, byDay[d]]; }).sort(function (a, b) { return a[1] - b[1]; }).slice(0, 5),
    hist: hist,
    style: [
      grp('불타기만 (오를 때 추가매수)', cycles.filter(function (c) { return c.pyramid > 0 && c.avgdown === 0; })),
      grp('한 번에 매수', cycles.filter(function (c) { return c.pyramid === 0 && c.avgdown === 0; })),
      grp('물타기 포함 (내릴 때 추가매수)', cycles.filter(function (c) { return c.avgdown > 0; }))
    ],
    entry: TB.map(function (l, i) { return grp(l, tb[i]); }),
    stair: { n: stair.length, pnl: sum(stair, pnlOf) },
    whatif: whatif,
    reentry: { n: reentry.length, higher: reentry.filter(function (r) { return r.higher; }).length, pnl: sum(reentry, function (r) { return r.pnl; }) },
    flipped: (function (g) { return { n: g.length, pnl: sum(g, pnlOf) }; })(L.filter(function (c) { return c.sells.some(function (s) { return s.ret > 0.02; }); })),
    kind: [grp('ETF', etfC), grp('개별주', stkC)],
    stockSellAmt: sum(rows.filter(function (r) { return r.side === 'S' && !isEtf(r.name); }), function (r) { return r.amt; }),
    totalAmt: sum(rows, function (r) { return r.amt; }),
    topLoss: cycles.slice().sort(function (a, b) { return a.pnl - b.pnl; }).slice(0, 12),
    topWin: cycles.slice().sort(function (a, b) { return b.pnl - a.pnl; }).slice(0, 8)
  };
}

/* ---------- 화면 ---------- */
var esc = function (s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); };
var man = function (v) { return (v > 0 ? '+' : v < 0 ? '-' : '') + Math.round(Math.abs(v) / 10000).toLocaleString() + '만원'; };
var pct = function (v, d) { var x = v * 100; return (x > 0 ? '+' : '') + x.toFixed(d == null ? 1 : d) + '%'; };
var rate = function (g) { return g.n ? Math.round(g.win / g.n * 100) + '%' : '–'; };
var cls = function (v) { return v > 0 ? 'jup' : v < 0 ? 'jdn' : ''; };
var UP = '#d93a3a', DN = '#2a6fd0';

var chartReady = null;
function loadChart() {
  if (root.Chart) return Promise.resolve();
  if (!chartReady) chartReady = new Promise(function (ok, no) {
    var s = document.createElement('script'); s.src = CHART_SRC; s.onload = ok; s.onerror = function () { chartReady = null; no(new Error('차트 라이브러리를 불러오지 못했습니다')); };
    document.head.appendChild(s);
  });
  return chartReady;
}

function reportHtml(A) {
  var n = A.cycles.length;
  if (!n) return '<p class="empty">끝까지 정리된(0주가 된) 거래가 없습니다. 체결내역 형식을 확인해 주세요.</p>';
  var st = A.style, pyr = st[0], ad = st[2];
  var payoff = A.avgLoss ? A.avgWin / -A.avgLoss : 0;
  var ent = A.entry.filter(function (g) { return g.n >= 5; });
  var bestE = ent.slice().sort(function (a, b) { return b.pnl - a.pnl; })[0];
  var early = A.entry.slice(0, 3), earlyG = { n: sum(early, function (g) { return g.n; }), pnl: sum(early, function (g) { return g.pnl; }) };
  var w7 = A.whatif[2], w5 = A.whatif[1];
  var stairShare = A.gl ? A.stair.pnl / A.gl : 0;
  var wd = A.worstDays.slice(0, 3);
  var fee = A.stockSellAmt * 0.002 + A.totalAmt * 0.00015;

  var head;
  if (ad.n && ad.pnl < 0 && ad.pnl <= Math.min(A.stair.pnl, 0) * 0.6) {
    head = '<b>매도 결단 부족도 보이지만, 가장 큰 구멍은 매수 쪽 "물타기"입니다.</b><br>' +
      '오를 때만 더 산 거래(불타기)는 <b class="' + cls(pyr.pnl) + '">' + man(pyr.pnl) + '</b>, 내릴 때 더 산 거래(물타기)는 <b class="' + cls(ad.pnl) + '">' + man(ad.pnl) + '</b>입니다.' +
      (ad.pnl < A.realized && A.realized < 0 ? ' 물타기 하나가 전체 실현손실보다 큽니다.' : '');
  } else {
    head = '<b>손실의 중심은 매도입니다.</b> 손실 거래 중 일부만 팔고 나머지를 더 싸게 판 "계단식 손절"이 손실의 <b>' + Math.round(stairShare * 100) + '%</b>(' + man(A.stair.pnl) + ')입니다.';
  }

  var tbl = function (list) {
    return '<tr><th>종목</th><th>기간</th><th class="num">보유</th><th class="num">손익</th><th class="num">수익률</th><th class="num">매수/매도</th><th class="num">물타기</th></tr>' +
      list.map(function (c) {
        return '<tr><td>' + esc(c.name) + '</td><td>' + c.start.slice(5) + '~' + c.end.slice(5) + '</td><td class="num">' + c.days + '일</td>' +
          '<td class="num ' + cls(c.pnl) + '">' + man(c.pnl) + '</td><td class="num ' + cls(c.ret) + '">' + pct(c.ret) + '</td>' +
          '<td class="num">' + c.buys.length + '/' + c.sells.length + '</td><td class="num">' + (c.avgdown ? c.avgdown + '회' : '–') + '</td></tr>';
      }).join('');
  };

  return '' +
    '<div class="stats">' +
      '<div class="stat"><div class="k">실현손익 (세전)</div><div class="v ' + cls(A.realized) + '">' + man(A.realized) + '</div></div>' +
      '<div class="stat"><div class="k">끝난 거래</div><div class="v">' + n + '<small>회</small></div></div>' +
      '<div class="stat"><div class="k">승률</div><div class="v">' + Math.round(A.win / n * 100) + '%<small> ' + A.win + '승 ' + A.loss + '패</small></div></div>' +
      '<div class="stat"><div class="k">평균 수익 / 평균 손실</div><div class="v"><span class="jup">' + pct(A.avgWin) + '</span> / <span class="jdn">' + pct(A.avgLoss) + '</span></div></div>' +
      '<div class="stat"><div class="k">손익비</div><div class="v">' + payoff.toFixed(2) + '<small> 배</small></div></div>' +
    '</div>' +
    '<div class="jnote">' + head + '</div>' +

    '<h3>① 누적 실현손익</h3><div class="jbox"><canvas id="jcCum"></canvas></div>' +
    '<p class="jp">가장 크게 잃은 날: ' + wd.map(function (d) { return d[0].slice(5).replace('-', '/') + ' <span class="jdn">' + man(d[1]) + '</span>'; }).join(', ') +
      '. 이 ' + wd.length + '일만 합쳐도 <b class="jdn">' + man(sum(wd, function (d) { return d[1]; })) + '</b>로, 손실이 시장 급락 며칠에 몰려 있습니다.</p>' +

    '<h3>② 월별 실현손익</h3><div class="jbox"><canvas id="jcMon"></canvas></div>' +

    '<h3>③ 거래별 수익률 분포</h3><div class="jbox"><canvas id="jcHist"></canvas></div>' +
    '<p class="jp">승률 ' + Math.round(A.win / n * 100) + '%로 이기려면 평균 수익이 평균 손실의 <b>' + (A.win ? (A.loss / A.win).toFixed(1) : '–') + '배</b>를 넘어야 본전입니다. 지금은 <b>' + payoff.toFixed(2) + '배</b>입니다. 15% 넘게 먹은 거래는 ' + n + '번 중 <b>' + A.big + '번</b>뿐입니다.</p>' +

    '<h3>④ 매도: 손절을 나눠서 하다가 더 잃음</h3><div class="jbox s"><canvas id="jcStair"></canvas></div>' +
    '<p class="jp">손실 거래 ' + A.loss + '건 중 <b>' + A.stair.n + '건</b>은 일부를 팔고 남은 물량을 더 낮은 가격에 마저 판 "계단식 손절"이었고, 손실의 <b>' + Math.round(stairShare * 100) + '%(' + man(A.stair.pnl) + ')</b>를 차지합니다. ' +
      '손실 거래의 첫 매도는 보통 ' + pct(A.firstSellLoss) + '에서 했지만, 가장 나쁜 매도는 ' + pct(A.worstSellLoss) + '까지 밀렸습니다(중앙값).</p>' +

    '<h3>⑤ 매도: 손절선을 지켰다면</h3><div class="jbox"><canvas id="jcWhat"></canvas></div>' +
    '<p class="jp">모든 매도를 그 손실선에서 끊었다고 가정한 계산입니다 (갭하락·미끄러짐 미반영이라 실제 효과는 더 작습니다). -7%면 <b class="jup">' + man(w7.saved) + '</b>, -5%면 <b class="jup">' + man(w5.saved) + '</b> 덜 잃었습니다.</p>' +

    '<h3>⑥ 매도: 수익을 너무 빨리 확정</h3>' +
    '<ul class="jul"><li>보유 기간 중앙값: 수익 거래 <b>' + A.medDaysWin + '일</b>, 손실 거래 <b>' + A.medDaysLoss + '일</b>.</li>' +
      '<li>전량 매도 후 7일 안에 같은 종목을 다시 산 경우 <b>' + A.reentry.n + '번</b>, 그중 <b>' + A.reentry.higher + '번</b>은 판 가격보다 비싸게 다시 샀습니다. 재진입 거래 합계 <b class="' + cls(A.reentry.pnl) + '">' + man(A.reentry.pnl) + '</b>.</li>' +
      '<li>수익 구간(+2% 이상)에서 일부를 팔고도 결국 손실로 끝난 거래 <b>' + A.flipped.n + '건</b> (' + man(A.flipped.pnl) + ').</li></ul>' +

    '<h3>⑦ 매수 방식별 결과</h3><div class="jbox s"><canvas id="jcStyle"></canvas></div>' +
    '<p class="jp">' + st.map(function (g) { return g.label.split(' (')[0] + ' ' + g.n + '건 · 승률 ' + rate(g) + ' · <span class="' + cls(g.pnl) + '">' + man(g.pnl) + '</span>'; }).join('<br>') + '</p>' +

    '<h3>⑧ 첫 매수 시간대별 결과</h3><div class="jbox"><canvas id="jcEntry"></canvas></div>' +
    '<p class="jp">장 시작 전~오전 11시 첫 매수 ' + earlyG.n + '건 합계 <b class="' + cls(earlyG.pnl) + '">' + man(earlyG.pnl) + '</b>' +
      (bestE ? ', 가장 좋았던 시간대는 <b>' + bestE.label + '</b>(' + bestE.n + '건 · 승률 ' + rate(bestE) + ' · <span class="' + cls(bestE.pnl) + '">' + man(bestE.pnl) + '</span>)' : '') + '입니다.</p>' +

    '<h3>⑨ 손실이 컸던 거래</h3><div class="twrap"><table>' + tbl(A.topLoss) + '</table></div>' +
    '<h3>수익이 컸던 거래</h3><div class="twrap"><table>' + tbl(A.topWin) + '</table></div>' +

    '<h3>매매 규칙 제안</h3><ol class="jul">' +
      '<li><b>손절은 한 번에, 전량.</b> 평단 대비 -7%(변동성 큰 종목은 -5%)에서 나눠 팔지 말고 다 팝니다. (-7% 기준 ' + man(w7.saved) + ' 차이)</li>' +
      '<li><b>물타기 금지.</b> 추가매수는 평단 위에서, 고점을 다시 뚫을 때만. (물타기 ' + ad.n + '건 ' + man(ad.pnl) + ')</li>' +
      '<li><b>수익은 추세선으로.</b> 목표 수익률 대신 10일선(또는 20일선) 종가 이탈 때만 팝니다. 반을 먼저 팔더라도 나머지는 추세 이탈까지.</li>' +
      '<li><b>진입은 확인하고.</b> 장전·장초반 돌파는 뒤집히기 쉬웠습니다.' + (bestE ? ' ' + bestE.label + '에도 신고가가 유지될 때 사는 편이 결과가 좋았습니다.' : '') + '</li>' +
      '<li><b>손절이 몰리는 주엔 신규 매수 쉬기.</b> 손절이 2~3번 연속 나오면 그 주는 새로 사지 않습니다.</li></ol>' +

    '<h3>계산 기준</h3><ul class="jul muted">' +
      '<li>체결 ' + A.rows.length + '건(매수 ' + A.nBuy + ' · 매도 ' + A.nSell + '), ' + A.period[0] + ' ~ ' + A.period[1] + '. 평균단가 기준이고, 같은 종목을 0주에서 사서 다시 0주가 될 때까지를 거래 1회로 셉니다.</li>' +
      '<li>수수료·세금 미반영. 개별주 매도 거래세(약 0.2%)와 수수료를 더하면 약 ' + man(fee).replace('+', '') + '이 추가 비용입니다.</li>' +
      (A.orphan.length ? '<li>매수 기록이 없는 매도 ' + A.orphan.length + '건(이전부터 보유하던 물량, 약 ' + man(sum(A.orphan, function (o) { return o.qty * o.price; })).replace('+', '') + ')은 매수가를 몰라 손익에서 뺐습니다.</li>' : '') +
      (A.openPos.length ? '<li>아직 보유 중인 ' + A.openPos.length + '종목은 미실현이라 거래 통계에서 뺐습니다 (부분 매도한 손익은 실현손익에 포함).</li>' : '') +
      (A.splits.length ? '<li>가격이 갑자기 1/N로 떨어진 매도는 무상증자·분할로 보고 수량을 보정했습니다: ' + A.splits.map(function (s) { return esc(s.name) + ' ' + s.date.slice(5) + ' ×' + s.factor; }).join(', ') + '.</li>' : '') +
    '</ul>';
}

var charts = [];
function drawCharts(A) {
  charts.forEach(function (c) { c.destroy(); }); charts = [];
  if (!A.cycles.length) return;
  var C = root.Chart;
  C.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif';
  C.defaults.color = '#6b7280'; C.defaults.borderColor = '#eef1f5';
  var pc = function (v) { return v >= 0 ? UP : DN; };
  var manTick = function (v) { return Math.round(v / 10000).toLocaleString() + '만'; };
  var $ = function (id) { return document.getElementById(id); };
  var bar = function (id, labels, vals, opt) {
    opt = opt || {};
    var horiz = opt.axis === 'y', vScale = {}, cScale = { grid: { display: false } };
    vScale.ticks = { callback: opt.count ? undefined : manTick };
    var scales = {}; scales[horiz ? 'x' : 'y'] = vScale; scales[horiz ? 'y' : 'x'] = cScale;
    charts.push(new C($(id), {
      type: 'bar',
      data: { labels: labels, datasets: [{ data: vals, backgroundColor: (opt.colors || vals).map(pc), borderRadius: 4, maxBarThickness: 44 }] },
      options: { maintainAspectRatio: false, indexAxis: horiz ? 'y' : 'x', plugins: { legend: { display: false }, tooltip: { callbacks: { label: opt.label || function (c) { return man(horiz ? c.parsed.x : c.parsed.y); } } } }, scales: scales }
    }));
  };
  charts.push(new C($('jcCum'), {
    type: 'line',
    data: { labels: A.cumSeries.map(function (x) { return x[0].slice(5); }), datasets: [{ data: A.cumSeries.map(function (x) { return x[1]; }), borderColor: '#1a3a6c', borderWidth: 2, pointRadius: 0, tension: 0.2, fill: { target: 'origin', above: 'rgba(217,58,58,.13)', below: 'rgba(42,111,208,.13)' } }] },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) { return '누적 ' + man(c.parsed.y); } } } }, scales: { x: { ticks: { maxTicksLimit: 9 }, grid: { display: false } }, y: { ticks: { callback: manTick } } } }
  }));
  bar('jcMon', A.monthly.map(function (m) { return +m[0].slice(5) + '월'; }), A.monthly.map(function (m) { return m[1]; }));
  bar('jcHist', A.hist.map(function (h) { return h.label; }), A.hist.map(function (h) { return h.n; }), {
    count: true, colors: A.hist.map(function (h) { return h.pnl; }),
    label: function (c) { var h = A.hist[c.dataIndex]; return h.n + '건 · 합계 ' + man(h.pnl); }
  });
  bar('jcStair', ['계단식 손절 (' + A.stair.n + '건)', '나머지 손실 (' + (A.loss - A.stair.n) + '건)'], [A.stair.pnl, A.gl - A.stair.pnl], { axis: 'y' });
  bar('jcWhat', A.whatif.map(function (w) { return w.label + ' 손절'; }), A.whatif.map(function (w) { return w.saved; }), {
    label: function (c) { var w = A.whatif[c.dataIndex]; return '덜 잃었을 금액 ' + man(w.saved) + ' · 해당 매도 ' + w.n + '건'; }
  });
  var gl = function (list) { return function (c) { var g = list[c.dataIndex]; return man(g.pnl) + ' · ' + g.n + '건 · 승률 ' + rate(g); }; };
  bar('jcStyle', A.style.map(function (g) { return g.label; }), A.style.map(function (g) { return g.pnl; }), { axis: 'y', label: gl(A.style) });
  bar('jcEntry', A.entry.map(function (g) { return g.label; }), A.entry.map(function (g) { return g.pnl; }), { label: gl(A.entry) });
}

/* ---------- 암호문 풀기 ---------- */
var b64 = function (s) { var bin = atob(s), u = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; };
async function loadEncrypted(sb) {
  var res = await fetch(ENC_URL + '?t=' + Date.now(), { cache: 'no-store' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('암호문을 불러오지 못했습니다 (' + res.status + ')');
  var enc = await res.json();
  var k = await sb.from('journal_secret').select('private_jwk').maybeSingle();
  if (k.error) throw new Error('열쇠를 불러오지 못했습니다: ' + k.error.message + ' — supabase/003_journal_secret.sql 실행 여부를 확인하세요.');
  if (!k.data) throw new Error('Supabase 에 열쇠가 없습니다 — supabase/003_journal_secret.sql 을 열쇠 값과 함께 실행하세요.');
  var subtle = root.crypto.subtle;
  var pri = await subtle.importKey('jwk', JSON.parse(k.data.private_jwk), { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['unwrapKey']);
  var aes = await subtle.unwrapKey('raw', b64(enc.wk), pri, { name: 'RSA-OAEP' }, { name: 'AES-GCM' }, false, ['decrypt']);
  var plain = await subtle.decrypt({ name: 'AES-GCM', iv: b64(enc.iv) }, aes, b64(enc.ct));
  var data = JSON.parse(new TextDecoder().decode(plain));
  return { rows: data.rows, source: data.source, updated: enc.updated };
}

/* ---------- 탭 연결 ---------- */
function mount(opt) {
  var sb = opt.client, $ = function (id) { return document.getElementById(id); };
  var el = { status: $('jStatus'), file: $('jFile'), text: $('jText'), save: $('jSave'), del: $('jDel'), preview: $('jPreview'), out: $('jOut') };
  var state = { loaded: false };

  function status(t) { el.status.innerHTML = t; }
  function render(text, label, given) {
    var rows = given || parse(text);
    if (!rows.length) { el.out.innerHTML = '<p class="empty">체결 줄을 하나도 찾지 못했습니다. "■ 매수 내역" / "■ 매도 내역" 아래에 "날짜 시각 종목 수량 단가 금액" 형식이어야 합니다.</p>'; return null; }
    var A = analyze(rows);
    el.out.innerHTML = (label ? '<p class="muted" style="margin-bottom:10px">' + label + '</p>' : '') + reportHtml(A);
    loadChart().then(function () { drawCharts(A); }).catch(function (e) { status('<span class="jdn">' + esc(e.message) + '</span>'); });
    return A;
  }

  var when = function (t) { return new Date(t).toLocaleString('ko-KR', { hour12: false }); };
  async function load() {
    status('불러오는 중…');
    var got = await Promise.all([
      loadEncrypted(sb).catch(function (e) { return { err: e.message }; }),
      sb.from('trade_journal').select('raw,file_name,updated_at').maybeSingle()
    ]);
    var enc = got[0], man = got[1], notes = [];
    if (enc && enc.err) { notes.push('<span class="jdn">' + esc(enc.err) + '</span>'); enc = null; }
    if (man.error) { notes.push('<span class="jdn">직접 올린 내역 불러오기 실패: <code>' + esc(man.error.message) + '</code></span>'); }
    var m = man.data;
    el.text.value = '';
    if (enc && (!m || enc.updated >= m.updated_at)) {
      status('반영된 내역: <b>' + esc(enc.source || 'Claude 가 올린 내역') + '</b> · ' + when(enc.updated) + (notes.length ? '<br>' + notes.join('<br>') : ''));
      render(null, '', enc.rows);
    } else if (m) {
      status('반영된 내역: <b>' + esc(m.file_name || '직접 붙여넣기') + '</b> (직접 올림) · ' + when(m.updated_at) + (notes.length ? '<br>' + notes.join('<br>') : ''));
      render(m.raw);
    } else {
      status((notes.length ? notes.join('<br>') + '<br>' : '') + '반영된 체결내역이 없습니다.');
      el.out.innerHTML = '';
    }
  }

  el.file.onchange = function () {
    var f = el.file.files[0]; if (!f) return;
    var rd = new FileReader();
    rd.onload = function () { el.text.value = rd.result; el.text.dataset.fname = f.name; status('파일을 읽었습니다: <b>' + esc(f.name) + '</b> — "미리 분석"으로 확인 후 "저장"하세요.'); };
    rd.readAsText(f, 'utf-8');
  };
  el.text.oninput = function () { delete el.text.dataset.fname; };
  el.preview.onclick = function () {
    if (!el.text.value.trim()) { el.text.focus(); return; }
    render(el.text.value, '⚠️ 아직 저장 전 미리보기입니다.');
  };
  el.save.onclick = async function () {
    var raw = el.text.value;
    if (!raw.trim()) { el.text.focus(); return; }
    if (!parse(raw).length) { render(raw); return; }
    el.save.disabled = true;
    var r = await sb.from('trade_journal').upsert({ owner: opt.userId, raw: raw, file_name: el.text.dataset.fname || null, updated_at: new Date().toISOString() });
    el.save.disabled = false;
    if (r.error) { status('<span class="jdn">저장 실패: <code>' + esc(r.error.message) + '</code></span>'); return; }
    el.file.value = '';
    load();
  };
  el.del.onclick = async function () {
    if (!confirm('저장된 체결내역을 삭제할까요? 되돌릴 수 없습니다.')) return;
    var r = await sb.from('trade_journal').delete().eq('owner', opt.userId);
    if (r.error) { status('<span class="jdn">삭제 실패: <code>' + esc(r.error.message) + '</code></span>'); return; }
    el.out.innerHTML = ''; load();
  };

  return { open: function () { if (!state.loaded) { state.loaded = true; load(); } } };
}

var api = { OWNER_EMAIL: OWNER_EMAIL, parse: parse, analyze: analyze, mount: mount };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
else root.Journal = api;
})(typeof window !== 'undefined' ? window : globalThis);
