/* 매매 복기 — 체결내역(txt) 파싱 · 거래 단위 손익 분석 · 차트
 * 체결내역은 Supabase trade_journal 테이블(마스터 본인만 읽기/쓰기, supabase/002_trade_journal.sql)에만 저장되고
 * 이 파일·저장소에는 들어가지 않습니다. */
(function (root) {
'use strict';

var OWNER_EMAIL = 'tyannytyanny@gmail.com';
var CHART_SRC = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js';
var ETF_PREFIX = ['ACE', 'KODEX', 'TIGER', 'PLUS', 'SOL', 'TIME', 'TIMEFOLIO', 'HANARO', 'KIWOOM', 'RISE', 'KOSEF', 'ARIRANG', 'HANA', 'WON', '1Q', 'BNK', 'FOCUS', 'TREX', 'UNICORN', 'KoAct', 'VITA', 'DAISHIN343', 'ITF', 'MASTER', 'KBSTAR'];

/* ---------- 파싱 ----------
 * "■ 매수 내역" / "■ 매도 내역" 아래의
 *   2026-01-05 12:53  한미반도체   18   158,800   2,858,400  [비고]
 * 형식 줄을 읽습니다. */
// 사명 변경 등으로 가격 DB(현재 사명 기준)와 이름이 다른 종목 → 같은 종목으로 합침
var ALIAS = { 'LIG넥스원': 'LIG디펜스앤에어로스페이스', 'PLUS 우주항공&UAM': 'PLUS 우주항공', '씨어스테크놀로지': '씨어스' };
var canon = function (n) { return ALIAS[n] || (n.indexOf('TIMEFOLIO ') === 0 ? 'TIME ' + n.slice(10) : n); };
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
    rows.push({ side: side, date: m[1], time: m[2], name: canon(m[3].trim()), qty: num(m[4]), price: num(m[5]), amt: num(m[6]), note: m[7] });
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
    r.avgBefore = p.q > 0 ? p.cost / p.q : null;   // 종목별 차트의 물타기·손절 판정용
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

    '<h3>종목별 매수·매도 지점</h3><div id="pvBox"></div>' +

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

/* ---------- 종목별 매수·매도 지점 차트 ----------
 * 가격: db/market/price(수정 종가, 종목·ETF) + db/market/ohlc(수정 시가·고가·저가, 일반 종목만 → ETF 는 종가선)
 * 같은 날 같은 방향 체결은 화살표 하나로 묶고, 체결 뒤 실제 주가 흐름으로 잘함/실수를 판정합니다. */
var PQ_SRC = '/tools/etf/hyparquet.min.js';
var V_GOOD = '#12a150', V_BAD = '#f07800', V_NEU = '#9aa1ad';
var pqReady = null;
function loadPq() {
  if (root.hyparquet) return Promise.resolve();
  if (!pqReady) pqReady = new Promise(function (ok, no) {
    var s = document.createElement('script'); s.src = PQ_SRC; s.onload = ok; s.onerror = function () { pqReady = null; no(new Error('가격 파일 해석기를 불러오지 못했습니다')); };
    document.head.appendChild(s);
  });
  return pqReady;
}
var monthAdd = function (mo, k) { var y = +mo.slice(0, 4), m = +mo.slice(5, 7) - 1 + k; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return y + '-' + (m < 9 ? '0' : '') + (m + 1); };
var monthsBetween = function (a, b) { var out = []; for (var m = a; m <= b; m = monthAdd(m, 1)) out.push(m); return out; };
var isoD = function (d) { return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10); };

var seriesCache = {};
async function loadSeries(names, firstDate, onProgress) {
  var key = names.slice().sort().join('|') + '|' + firstDate;
  if (seriesCache[key]) return seriesCache[key];
  await loadPq();
  var want = {}; names.forEach(function (n) { want[n] = 1; });
  var now = new Date(), cur = now.getFullYear() + '-' + (now.getMonth() < 9 ? '0' : '') + (now.getMonth() + 1);
  var m0 = firstDate.slice(0, 7);
  var pMonths = monthsBetween(monthAdd(m0, -13), cur), oMonths = monthsBetween(monthAdd(m0, -2), cur);
  var jobs = pMonths.map(function (m) { return ['price', m, ['date', 'name', 'close']]; })
    .concat(oMonths.map(function (m) { return ['ohlc', m, ['date', 'name', 'open', 'high', 'low']]; }));
  var done = 0, S = {};
  var get = function (n) { return S[n] || (S[n] = {}); };
  // 동시에 4개씩
  var queue = jobs.slice();
  async function worker() {
    while (queue.length) {
      var j = queue.shift();
      try {
        var res = await fetch('/db/market/' + j[0] + '/' + j[1] + '.parquet');
        if (res.ok) {
          var rows = await root.hyparquet.parquetReadObjects({ file: await res.arrayBuffer(), columns: j[2] });
          for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            if (!want[r.name]) continue;
            var day = get(r.name), d = isoD(r.date), o = day[d] || (day[d] = {});
            if (j[0] === 'price') o.c = r.close; else { o.o = r.open; o.h = r.high; o.l = r.low; }
          }
        }
      } catch (e) { /* 없는 달은 건너뜀 */ }
      done++; if (onProgress) onProgress(done, jobs.length);
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()]);
  var out = {};
  Object.keys(S).forEach(function (n) {
    var ds = Object.keys(S[n]).filter(function (d) { return S[n][d].c > 0; }).sort();
    out[n] = ds.map(function (d) {
      var o = S[n][d], c = o.c;
      var ok = o.h > 0 && o.l > 0 && o.l <= c * 1.001 && o.h >= c * 0.999;   // 고가·저가가 종가를 감싸지 않으면(분할 미반영 등) 종가만 사용
      return { d: d, o: ok ? o.o : c, h: ok ? o.h : c, l: ok ? o.l : c, c: c, ohlc: ok };
    });
  });
  seriesCache[key] = out;
  return out;
}

function evaluate(A, S) {
  // 같은 날·같은 방향 체결을 하나로
  var groups = {}, order = [];
  A.rows.forEach(function (r) {
    var k = r.name + '|' + r.date + '|' + r.side;
    var g = groups[k];
    if (!g) { g = groups[k] = { name: r.name, date: r.date, side: r.side, qty: 0, amt: 0, n: 0, avg: r.avgBefore, time: r.time }; order.push(g); }
    g.qty += r.qty; g.amt += r.amt; g.n++;
  });
  var byName = {};
  order.forEach(function (g) {
    g.price = g.amt / g.qty;
    var s = S[g.name];
    if (!s || !s.length) { g.v = 'na'; return; }
    var i = 0; while (i < s.length && s[i].d < g.date) i++;
    if (i >= s.length) { g.v = 'na'; return; }
    g.i = i;
    var f = g.price / s[i].c;                       // 체결가 ÷ 수정 종가 → 무상증자·분할 이전 체결은 배율로 환산
    g.f = Math.abs(f - 1) > 0.3 ? f : 1;   // 30% 넘게 어긋나면 그날 수정 종가 위치에 표시
    var px = g.price / g.f;
    g.px = px;
    var hi = 0; for (var k = Math.max(0, i - 252); k < i; k++) hi = Math.max(hi, s[k].c);
    g.near = hi > 0 && px >= hi * 0.97;
    var fut = s.slice(i + 1, i + 21);
    g.fwd = fut.length;
    g.f20 = fut.length ? fut[fut.length - 1].c / px - 1 : null;
    g.v = 'neu'; g.why = '';
    if (g.side === 'B') {
      var low10 = Infinity; fut.slice(0, 10).forEach(function (x) { low10 = Math.min(low10, x.l); });
      g.low10 = isFinite(low10) ? low10 / px - 1 : null;
      if (g.avg && g.price < g.avg * 0.99) { g.v = 'bad'; g.kind = '물타기'; g.why = '평단(' + Math.round(g.avg).toLocaleString() + ')보다 싸게 추가 매수'; }
      else if (g.low10 != null && g.low10 <= -0.07 && g.f20 < 0) { g.v = 'bad'; g.kind = g.near ? '진입 직후 급락' : '신고가 전 이른 진입'; g.why = '10일 안에 ' + pct(g.low10, 0) + '까지 밀리고 20일 뒤 ' + pct(g.f20, 0) + (g.near ? '' : ' · 신고가 근처가 아닌 곳에서 진입'); }
      else if (g.f20 != null && g.f20 >= 0.05) { g.v = 'good'; g.kind = g.near ? '신고가 매수 성공' : '매수 성공'; g.why = '20거래일 뒤 ' + pct(g.f20, 0) + (g.near ? ' · 신고가 근처 매수' : ''); }
      else g.why = g.f20 == null ? '이후 데이터 없음' : '20거래일 뒤 ' + pct(g.f20, 0);
    } else {
      var mx = 0; fut.forEach(function (x) { mx = Math.max(mx, x.h); });
      g.mx = fut.length ? mx / px - 1 : null;
      g.ret = g.avg ? g.price / g.avg - 1 : null;
      if (g.ret != null && g.ret <= -0.07) { g.v = 'bad'; g.kind = '손절 지연'; g.why = '평단 대비 ' + pct(g.ret, 1) + '에서 매도 (-7% 넘김)'; }
      else if (g.mx != null && g.mx >= 0.15 && (g.ret == null || g.ret >= 0)) { g.v = 'bad'; g.kind = '이른 익절'; g.why = '판 뒤 20일 안에 ' + pct(g.mx, 0) + ' 더 오름'; }
      else if (g.f20 != null && g.f20 <= -0.05) { g.v = 'good'; g.kind = g.ret != null && g.ret < 0 ? '잘한 손절' : '잘한 매도'; g.why = '판 뒤 20거래일 ' + pct(g.f20, 0) + (g.ret != null ? ' · 평단 대비 ' + pct(g.ret, 1) : ''); }
      else g.why = (g.ret != null ? '평단 대비 ' + pct(g.ret, 1) + ' · ' : '') + (g.f20 == null ? '이후 데이터 없음' : '판 뒤 20거래일 ' + pct(g.f20, 0));
    }
    (byName[g.name] = byName[g.name] || []).push(g);
  });
  var pnl = {};
  A.sells.forEach(function (x) { pnl[x.name] = (pnl[x.name] || 0) + x.pnl; });
  var stocks = Object.keys(byName).map(function (n) {
    var m = byName[n];
    return { name: n, marks: m, pnl: pnl[n] || 0, good: m.filter(function (x) { return x.v === 'good'; }).length, bad: m.filter(function (x) { return x.v === 'bad'; }).length };
  }).sort(function (a, b) { return a.pnl - b.pnl; });
  var all = order.filter(function (g) { return g.v !== 'na'; });
  var kinds = {};
  all.forEach(function (g) { if (g.kind) { var k = kinds[g.kind] || (kinds[g.kind] = { kind: g.kind, v: g.v, side: g.side, n: 0 }); k.n++; } });
  var buys = all.filter(function (g) { return g.side === 'B' && g.fwd >= 10; });
  var rateOf = function (list, v) { return list.length ? list.filter(function (g) { return g.v === v; }).length / list.length : 0; };
  var nearB = buys.filter(function (g) { return g.near; }), farB = buys.filter(function (g) { return !g.near; });
  return {
    stocks: stocks, S: S, all: all, na: order.length - all.length,
    kinds: Object.keys(kinds).map(function (k) { return kinds[k]; }).sort(function (a, b) { return b.n - a.n; }),
    near: { n: nearB.length, bad: rateOf(nearB, 'bad'), good: rateOf(nearB, 'good') },
    far: { n: farB.length, bad: rateOf(farB, 'bad'), good: rateOf(farB, 'good') }
  };
}

function pvSummaryHtml(E) {
  var b = E.all.filter(function (g) { return g.side === 'B'; }), s = E.all.filter(function (g) { return g.side === 'S'; });
  var cnt = function (l, v) { return l.filter(function (g) { return g.v === v; }).length; };
  var chip = function (k) { return '<span class="pvk" style="border-color:' + (k.v === 'good' ? V_GOOD : V_BAD) + '"><i style="background:' + (k.v === 'good' ? V_GOOD : V_BAD) + '"></i>' + (k.side === 'B' ? '매수 · ' : '매도 · ') + esc(k.kind) + ' <b>' + k.n + '</b></span>'; };
  return '<div class="stats">' +
    '<div class="stat"><div class="k">매수 판정</div><div class="v"><span style="color:' + V_GOOD + '">잘함 ' + cnt(b, 'good') + '</span> · <span style="color:' + V_BAD + '">실수 ' + cnt(b, 'bad') + '</span><small> / ' + b.length + '</small></div></div>' +
    '<div class="stat"><div class="k">매도 판정</div><div class="v"><span style="color:' + V_GOOD + '">잘함 ' + cnt(s, 'good') + '</span> · <span style="color:' + V_BAD + '">실수 ' + cnt(s, 'bad') + '</span><small> / ' + s.length + '</small></div></div>' +
    '<div class="stat"><div class="k">신고가 근처 매수 실패율</div><div class="v">' + Math.round(E.near.bad * 100) + '%<small> ' + E.near.n + '회</small></div></div>' +
    '<div class="stat"><div class="k">그 외 매수 실패율</div><div class="v">' + Math.round(E.far.bad * 100) + '%<small> ' + E.far.n + '회</small></div></div>' +
    '</div><div class="pvks">' + E.kinds.map(chip).join('') + '</div>' +
    '<p class="jp">판정 기준 — 매수: 평단보다 싸게 추가하면 <b>물타기</b>, 10거래일 안에 -7% 이상 밀리고 20거래일 뒤에도 손실이면 <b>진입 실패</b>(52주 신고가 3% 이내가 아니면 "신고가 전 이른 진입"), 20거래일 뒤 +5% 이상이면 <b>성공</b>. ' +
    '매도: 평단 대비 -7%보다 더 잃고 팔면 <b>손절 지연</b>, 이익 매도 후 20거래일 안에 +15% 넘게 더 오르면 <b>이른 익절</b>, 판 뒤 20거래일에 -5% 이상 빠지면 <b>잘한 매도</b>.</p>';
}

function pvPickerHtml(E) {
  return '<div class="ctl" style="margin:10px 0 6px"><input type="text" id="pvQ" placeholder="종목 검색"><select id="pvSort"><option value="pnl">손익 나쁜 순</option><option value="bad">실수 많은 순</option><option value="good">잘한 것 많은 순</option><option value="name">이름순</option></select></div>' +
    '<div class="pvlist" id="pvList"></div>' +
    '<div id="pvChart" class="pvchart"></div><div id="pvTip" class="pvtip"></div><div class="twrap" id="pvTrades"></div>';
}

function pvListHtml(E, q, sort) {
  var list = E.stocks.filter(function (x) { return !q || x.name.toLowerCase().indexOf(q) >= 0; });
  list = list.slice().sort(sort === 'bad' ? function (a, b) { return b.bad - a.bad || a.pnl - b.pnl; } : sort === 'good' ? function (a, b) { return b.good - a.good || b.pnl - a.pnl; } : sort === 'name' ? function (a, b) { return a.name < b.name ? -1 : 1; } : function (a, b) { return a.pnl - b.pnl; });
  return list.map(function (x) {
    return '<button class="pvi" data-n="' + esc(x.name) + '"><span class="pvn">' + esc(x.name) + '</span><span class="' + cls(x.pnl) + '">' + man(x.pnl) + '</span>' +
      '<span class="pvc"><b style="color:' + V_GOOD + '">✓' + x.good + '</b> <b style="color:' + V_BAD + '">✗' + x.bad + '</b></span></button>';
  }).join('') || '<p class="empty">해당 종목이 없습니다</p>';
}

function pvChartSvg(st, s, width) {
  var marks = st.marks.filter(function (g) { return g.i != null; });
  if (!marks.length) return { svg: '<p class="empty">가격 데이터가 없습니다</p>', marks: [] };
  var i0 = Math.max(0, marks[0].i - 25), i1 = Math.min(s.length - 1, marks[marks.length - 1].i + 25);
  var bars = s.slice(i0, i1 + 1), n = bars.length;
  var W = Math.max(320, Math.round(width || 1000)), H = W < 640 ? 300 : 380, L = 6, R = W < 640 ? 52 : 62, T = 14, B = 34, pw = W - L - R, ph = H - T - B;
  var lo = Infinity, hi = -Infinity;
  bars.forEach(function (b) { lo = Math.min(lo, b.l); hi = Math.max(hi, b.h); });
  marks.forEach(function (g) { lo = Math.min(lo, g.px); hi = Math.max(hi, g.px); });
  var pad = (hi - lo) * 0.12 || hi * 0.05; lo -= pad; hi += pad;
  var x = function (k) { return L + (k + 0.5) * pw / n; }, y = function (v) { return T + (hi - v) / (hi - lo) * ph; };
  var bw = Math.max(1, Math.min(9, pw / n * 0.62));
  var g = '';
  // 가로 눈금 4개
  for (var t = 0; t <= 4; t++) {
    var v = lo + (hi - lo) * t / 4, yy = y(v);
    g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + yy + '" y2="' + yy + '" stroke="#eef1f5"/><text x="' + (W - R + 6) + '" y="' + (yy + 4) + '" font-size="11" fill="#9099a6">' + Math.round(v).toLocaleString() + '</text>';
  }
  // 월 눈금
  var lastM = '';
  bars.forEach(function (b, k) {
    var m = b.d.slice(0, 7);
    if (m !== lastM) { lastM = m; if (k < 3) return; g += '<line x1="' + x(k) + '" x2="' + x(k) + '" y1="' + T + '" y2="' + (H - B) + '" stroke="#f3f4f7"/><text x="' + x(k) + '" y="' + (H - B + 16) + '" font-size="11" fill="#9099a6" text-anchor="middle">' + (+m.slice(5)) + '월</text>'; }
  });
  var anyOhlc = bars.some(function (b) { return b.ohlc; });
  if (anyOhlc) {
    bars.forEach(function (b, k) {
      var up = b.c >= b.o, col = up ? UP : DN, xx = x(k);
      g += '<line x1="' + xx + '" x2="' + xx + '" y1="' + y(b.h) + '" y2="' + y(b.l) + '" stroke="' + col + '" stroke-width="1"/>' +
        '<rect x="' + (xx - bw / 2) + '" y="' + y(Math.max(b.o, b.c)) + '" width="' + bw + '" height="' + Math.max(1, Math.abs(y(b.o) - y(b.c))) + '" fill="' + (up ? col : '#fff') + '" stroke="' + col + '"/>';
    });
  } else {
    g += '<polyline fill="none" stroke="#1a3a6c" stroke-width="2" points="' + bars.map(function (b, k) { return x(k) + ',' + y(b.c); }).join(' ') + '"/>';
  }
  // 화살표: 매수 ▲ (체결가 아래), 매도 ▼ (체결가 위)
  var arr = '';
  marks.forEach(function (m, idx) {
    var k = m.i - i0; if (k < 0 || k >= n) return;
    var xx = x(k), yy = y(m.px), col = m.v === 'good' ? V_GOOD : m.v === 'bad' ? V_BAD : V_NEU;
    var p = m.side === 'B'
      ? [xx, yy + 3, xx - 7, yy + 15, xx - 2.5, yy + 15, xx - 2.5, yy + 24, xx + 2.5, yy + 24, xx + 2.5, yy + 15, xx + 7, yy + 15]
      : [xx, yy - 3, xx - 7, yy - 15, xx - 2.5, yy - 15, xx - 2.5, yy - 24, xx + 2.5, yy - 24, xx + 2.5, yy - 15, xx + 7, yy - 15];
    var pts = []; for (var q = 0; q < p.length; q += 2) pts.push(p[q].toFixed(1) + ',' + p[q + 1].toFixed(1));
    arr += '<g class="pva" data-k="' + idx + '"><circle cx="' + xx + '" cy="' + yy + '" r="2.4" fill="' + col + '"/><polygon points="' + pts.join(' ') + '" fill="' + col + '" stroke="#fff" stroke-width="1.2"/>' +
      '<rect x="' + (xx - 10) + '" y="' + (m.side === 'B' ? yy : yy - 26) + '" width="20" height="26" fill="transparent"/></g>';
  });
  return { svg: '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block">' + g + arr + '</svg>', marks: marks };
}

function markText(m) {
  return '<b>' + m.date + ' ' + (m.side === 'B' ? '매수' : '매도') + '</b> ' + m.qty.toLocaleString() + '주 × ' + Math.round(m.price).toLocaleString() + '원' + (m.n > 1 ? ' (' + m.n + '회 체결)' : '') +
    (m.f !== 1 ? ' <span class="muted">· 차트는 무상증자·분할 환산가 ' + Math.round(m.px).toLocaleString() + '원</span>' : '') +
    '<br><span style="color:' + (m.v === 'good' ? V_GOOD : m.v === 'bad' ? V_BAD : '#6b7280') + ';font-weight:700">' + (m.v === 'good' ? '✓ ' : m.v === 'bad' ? '✗ ' : '– ') + esc(m.kind || '보통') + '</span> ' + esc(m.why || '');
}

function mountPriceView(A, box) {
  var names = Object.keys(A.rows.reduce(function (o, r) { o[r.name] = 1; return o; }, {}));
  box.innerHTML = '<p class="muted" id="pvLoad">종목별 주가를 불러오는 중… (처음 한 번만 조금 걸립니다)</p>';
  loadSeries(names, A.period[0], function (d, t) { var e = document.getElementById('pvLoad'); if (e) e.textContent = '종목별 주가를 불러오는 중… ' + d + ' / ' + t; })
    .then(function (S) {
      var E = evaluate(A, S);
      box.innerHTML = pvSummaryHtml(E) + pvPickerHtml(E) + (E.na ? '<p class="muted">가격 DB에 없는 체결 ' + E.na + '건은 차트·판정에서 빠졌습니다.</p>' : '');
      var $ = function (id) { return document.getElementById(id); };
      var cur = null;
      function list() {
        $('pvList').innerHTML = pvListHtml(E, $('pvQ').value.trim().toLowerCase(), $('pvSort').value);
        $('pvList').querySelectorAll('.pvi').forEach(function (b) { b.classList.toggle('on', b.dataset.n === cur); b.onclick = function () { show(b.dataset.n); }; });
      }
      function show(name) {
        cur = name; list();
        var st = E.stocks.filter(function (x) { return x.name === name; })[0];
        var c = pvChartSvg(st, S[name] || [], $('pvChart').clientWidth - 18);
        $('pvChart').innerHTML = '<div class="pvhead"><b>' + esc(name) + '</b> <span class="' + cls(st.pnl) + '">' + man(st.pnl) + '</span>' +
          '<span class="pvleg"><i style="color:' + V_GOOD + '">▲▼ 잘함</i><i style="color:' + V_BAD + '">▲▼ 실수</i><i style="color:' + V_NEU + '">▲▼ 보통</i> · ▲매수 ▼매도</span></div>' + c.svg;
        $('pvTip').innerHTML = '<span class="muted">화살표를 누르면 그 매매의 판정 이유가 보입니다.</span>';
        $('pvTrades').innerHTML = '<table><tr><th>날짜</th><th>구분</th><th class="num">수량</th><th class="num">단가</th><th>판정</th><th>이유</th></tr>' +
          st.marks.map(function (m, k) {
            return '<tr data-k="' + k + '"><td>' + m.date.slice(5) + '</td><td>' + (m.side === 'B' ? '<b class="jup">매수</b>' : '<b class="jdn">매도</b>') + '</td><td class="num">' + m.qty.toLocaleString() + '</td><td class="num">' + Math.round(m.price).toLocaleString() + '</td>' +
              '<td style="color:' + (m.v === 'good' ? V_GOOD : m.v === 'bad' ? V_BAD : '#6b7280') + ';font-weight:700">' + (m.v === 'good' ? '✓ ' : m.v === 'bad' ? '✗ ' : m.v === 'na' ? '' : '– ') + esc(m.kind || (m.v === 'na' ? '가격 없음' : '보통')) + '</td><td class="muted" style="white-space:normal;min-width:180px">' + esc(m.why || '') + '</td></tr>';
          }).join('') + '</table>';
        $('pvChart').querySelectorAll('.pva').forEach(function (a) {
          var m = c.marks[+a.dataset.k];
          a.onmouseenter = a.onclick = function () {
            $('pvTip').innerHTML = markText(m);
            $('pvChart').querySelectorAll('.pva').forEach(function (z) { z.classList.toggle('on', z === a); });
          };
        });
      }
      $('pvQ').oninput = list; $('pvSort').onchange = list;
      list();
      if (E.stocks.length) show(E.stocks[0].name);
    })
    .catch(function (e) { box.innerHTML = '<p class="jdn">주가를 불러오지 못했습니다: ' + esc(e.message) + '</p>'; });
}

/* ---------- 탭 연결 ---------- */
function mount(opt) {
  var sb = opt.client, $ = function (id) { return document.getElementById(id); };
  var el = { status: $('jStatus'), file: $('jFile'), text: $('jText'), save: $('jSave'), del: $('jDel'), preview: $('jPreview'), out: $('jOut') };
  var state = { loaded: false };

  function status(t) { el.status.innerHTML = t; }
  // 응답이 없으면 15초 뒤 오류로 끝냄 (무한 "불러오는 중" 방지)
  function timed(p) {
    return Promise.race([p, new Promise(function (ok) {
      setTimeout(function () { ok({ error: { message: '15초 동안 응답이 없습니다. 새로고침 후 다시 시도해 주세요.' } }); }, 15000);
    })]);
  }
  function render(text, label) {
    var rows = parse(text);
    if (!rows.length) { el.out.innerHTML = '<p class="empty">체결 줄을 하나도 찾지 못했습니다. "■ 매수 내역" / "■ 매도 내역" 아래에 "날짜 시각 종목 수량 단가 금액" 형식이어야 합니다.</p>'; return null; }
    var A = analyze(rows);
    el.out.innerHTML = (label ? '<p class="muted" style="margin-bottom:10px">' + label + '</p>' : '') + reportHtml(A);
    loadChart().then(function () { drawCharts(A); }).catch(function (e) { status('<span class="jdn">' + esc(e.message) + '</span>'); });
    if (document.getElementById('pvBox')) mountPriceView(A, document.getElementById('pvBox'));
    return A;
  }

  async function load() {
    status('불러오는 중…');
    var r = await timed(sb.from('trade_journal').select('raw,file_name,updated_at').maybeSingle());
    if (r.error) { status('<span class="jdn">불러오기 실패: <code>' + esc(r.error.message) + '</code> — Supabase 에 <code>supabase/002_trade_journal.sql</code> 을 실행했는지 확인하세요.</span>'); return; }
    if (!r.data) { status('저장된 체결내역이 없습니다. 아래에서 파일을 고르거나 붙여넣고 저장하세요.'); el.out.innerHTML = ''; return; }
    status('저장된 내역: <b>' + esc(r.data.file_name || '붙여넣기') + '</b> · ' + new Date(r.data.updated_at).toLocaleString('ko-KR', { hour12: false }));
    el.text.value = '';
    render(r.data.raw);
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
    var r = await timed(sb.from('trade_journal').upsert({ owner: opt.userId, raw: raw, file_name: el.text.dataset.fname || null, updated_at: new Date().toISOString() }));
    el.save.disabled = false;
    if (r.error) { status('<span class="jdn">저장 실패: <code>' + esc(r.error.message) + '</code></span>'); return; }
    el.file.value = '';
    load();
  };
  el.del.onclick = async function () {
    if (!confirm('저장된 체결내역을 삭제할까요? 되돌릴 수 없습니다.')) return;
    var r = await timed(sb.from('trade_journal').delete().eq('owner', opt.userId));
    if (r.error) { status('<span class="jdn">삭제 실패: <code>' + esc(r.error.message) + '</code></span>'); return; }
    el.out.innerHTML = ''; load();
  };

  return { open: function () { if (!state.loaded) { state.loaded = true; load(); } } };
}

var api = { OWNER_EMAIL: OWNER_EMAIL, parse: parse, analyze: analyze, evaluate: evaluate, mount: mount };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
else root.Journal = api;
})(typeof window !== 'undefined' ? window : globalThis);
