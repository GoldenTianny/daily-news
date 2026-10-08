/* 매수·매도 원칙 — 관리자 '매매 복기' 옆 탭 (마스터 본인 전용)
 * 보유 종목·평단은 Supabase trade_journal(매매 복기에 저장한 체결내역)에서 자동 계산하고,
 * 비중(R)·초기 손절가·메모 같은 운용 설정은 이 브라우저(localStorage)에 둡니다.
 * 매도선은 가격 DB(db/market/price) 종가로 매일 다시 계산됩니다. */
(function (root) {
'use strict';

var PQ_SRC = '/tools/etf/hyparquet.min.js';
var LS_KEY = 'gj_rules_meta_v1';
var MAX_DAYS_PEAK = 60;          // 고점: 진입일 이후(진입일을 모르면 최근 60거래일) 수정 고가 최고가 — 고가 DB가 없으면 종가
var ARM_PCT = 0.10;              // 고점(고가)이 평단 +10% 를 넘긴 뒤부터 본전/고점−15% 규칙 (+5%는 검증상 휩소 과다)
var TRAIL = 0.15;                // 고점 대비 −15%
var INIT_STOP = 0.07;            // 초기 손절가 미지정 시 −7%
var BIG_LOW_DATE = '2026-07-30'; // 메모리 대형주 저점(사이클 손절 기준)

/* ---------- 보유 종목 기본 설정 (체결내역에 없을 때의 평단 · 비중 · 초기 손절 · 메모) ----------
 * 2026-10-06 기준. 체결내역이 저장돼 있으면 평단·수량·분할 진행은 체결내역이 우선합니다. */
var DEFAULT_META = {
  '피에스케이홀딩스': { cost: 170482, r: 2, memo: '1/3 매도 (+20%, 10/6)' },
  '심텍':        { cost: 145552, r: 2, memo: '1/3 매도 (+20%, 10/6)' },
  'HPSP':       { cost: 56747,  r: 1, memo: '1/3 매도 (+20%)' },
  '인텍플러스':    { cost: 48878,  r: 1, memo: '1/3 매도 (+20%)' },
  '티에스이':      { cost: 282360, r: 1, memo: '' },
  '컴투스':       { cost: 37838,  r: 1, stop: 36200, since: '2026-10-02', memo: '구글플레이 매출 순위 5위 밖이면 손절선과 무관하게 정리' },
  '삼성전기':      { cost: 1574000, r: 2, stop: 1462000, since: '2026-10-02', memo: '7월 반등 고점 1,828,000 종가 돌파 전까지는 손절선 하나만' },
  '씨젠':        { cost: 35887,  r: 0.5, stop: 33100, since: '2026-10-02', memo: '' },
  '코스맥스':      { cost: 305200, r: 1, stop: 264000, since: '2026-10-07', memo: '10/6 박스 돌파 다음 날 진입 · 손절 = 돌파일 저가 아래' }
};

/* 체결내역에 남아 있어도 표에서 빼는 종목 (전량 매도 완료 등) */
var DEFAULT_HIDE = { 'KODEX 구리': '2026-10-06 전량 매도', '가온전선': '2026-10-08 시가 전량 매도 (본전선 이탈)' };

/* ---------- 원칙 본문 ---------- */
var RULES = [
  ['+20% 도달 → 1/3 매도', '종가가 평단 +20%를 넘으면 다음 거래일에 1/3을 판다. 다음 날 수익률이 조금 낮아져도 그냥 실행한다. "다시 +20% 오면 팔지"로 미루면 규칙이 재량으로 바뀐다.', '이것만으로 승률 67% → 77%, 수익을 전부 반납하고 손실로 끝나는 비율 28% → 17%.'],
  ['+40% 도달 → 남은 것의 절반 매도', '종가가 평단 +40%를 넘으면 남은 물량의 절반을 더 판다. 이 시점이면 원금은 이미 전부 회수된 상태다.', '중앙값 +20.2%, +30% 이상으로 끝나는 비율 39%. 그냥 보유(45%)와 큰 차이 없이 최악을 −14%로 자른다.'],
  ['나머지 → 본전선 또는 최근 고점 −15% 중 높은 쪽 이탈 시 전량 매도', '종가 기준이다. 주가가 새 고점을 찍으면 −15% 선도 같이 올린다. 내려도 선은 내리지 않는다. 수익이 얕은 종목은 본전선이 먼저 걸리고, 그게 규칙의 역할이다. <b>단, 막 들어간 종목은 예외</b> — 고점(장중 고가)이 평단 <b>+10%</b>를 한 번 넘기 전까지는 본전선이 아니라 진입할 때 정한 손절선(직전 눌림 저점, 없으면 −7%)을 쓴다. 검증: +5% 단계에서 본전선을 걸면 승률 41%·중앙값 −0.9%로 절반이 본전에서 끊긴 뒤 다시 오르고, +10% 단계부터 걸면 승률 60%·중앙값 +9.5%·최악 −14%로 안정된다.', '최악 −14.4%, 손실로 끝나는 비율 6%. 20일선 2일 연속 이탈과 결과가 비슷하지만 최악이 더 얕다.'],
  ['10일선은 경계선, 재매수 금지', '10일선 아래에서는 추가 매수 금지. 10일선 이탈 매도 + 회복 시 재매수는 검증에서 평균 +8.7%, 승률 50%, 최악 −68%로 가장 나빴다. 판 물량을 다시 사는 유일한 조건은 신고가 돌파다.', ''],
  ['수직 상승 종목은 먼저 절반', '20거래일에 +60% 이상 오른 종목은 규칙과 무관하게 절반을 먼저 챙긴다. 과거 고점에서 이런 종목은 −15% 선을 하루 만에 뚫고 내려갔다.', ''],
  ['사이클 경고가 켜지면 전체 절반 축소', '메모리 대형주(삼성전자·SK하이닉스)가 7/30 저점을 깨거나 소부장 신고가 종목 비율이 40%를 넘으면 종목별 규칙과 무관하게 보유 전체를 절반으로 줄인다. 아래 "사이클 경고 신호"에서 자동 확인.', '']
];

var BACKTEST = [
  ['그냥 보유', '+39.8%', '+20.9%', '67%', '−61.7%', '28%', '45%', ''],
  ['10일선 이탈 즉시 매도', '+19.0%', '+13.5%', '91%', '−17.2%', '3%', '7%', ''],
  ['10일선 매도 후 회복 시 재매수', '+8.7%', '+0.3%', '50%', '−68.4%', '44%', '14%', 'bad'],
  ['+20%에 1/3 매도, 나머지 그냥 보유', '+34.4%', '+22.7%', '77%', '−56.3%', '17%', '42%', ''],
  ['고점 −15% 또는 본전 이탈 시 전량 매도', '+22.3%', '+13.2%', '77%', '−14.4%', '6%', '29%', ''],
  ['+20% 1/3, +40% 절반, 나머지 고점 −15%/본전 (채택)', '+21.9%', '+20.2%', '82%', '−14.4%', '6%', '39%', 'pick'],
  ['+20% 1/3, 나머지 20일선 2일 이탈/본전', '+21.8%', '+16.8%', '84%', '−14.4%', '5%', '28%', '']
];

var BUY_STATS = [
  ['보통 돌파 (120일 +20~100% 뒤 신고가)', '8,285', '+1.9%', '55%', '−7.3%', '31%', ''],
  ['급등 뒤 돌파 (120일 +300% · 20일 +40% 뒤 신고가) — 가온전선 유형', '278', '−20.8%', '33%', '−32.3%', '77%', 'bad'],
  ['무너진 주도주의 박스 상단 돌파 (52주 고점 −20~−40%, RS 90+) — 삼성전기 유형', '307', '−9.6%', '36%', '−22.9%', '78%', 'bad'],
  ['와인스타인 RS 제로선 "직전"(−12~0, 상승 중)에서 미리 매수', '6,360', '+1.0%', '53%', '−8.2%', '20일 내 실제 돌파 41% (제로선에서 멀면 29%)', '']
];

var BUY_RULES = [
  '<b>진입 신호는 셋 중 하나</b>: ① 와인스타인 RS 제로선 상향 돌파 종가 → 다음 날 ② 돌파 후 첫 10일선 눌림 반등 ③ 52주 신고가 돌파 종가 → 다음 날. 그 외는 신호가 아니다.',
  '<b>10배 오른 종목의 신고가 돌파에는 불타기하지 않는다.</b> 10건 중 8건이 40일 안에 15% 넘게 밀린다. 두 번째 진입 자리는 돌파가 아니라 20일선 눌림이다.',
  '<b>−30% 빠진 옛 주도주가 박스 상단을 넘는 건 매수 신호가 아니다.</b> 위에 쌓인 매물이 반등마다 나온다. 직전 반등 고점을 종가로 넘고 와인스타인 RS가 다시 오르기 시작할 때 본다.',
  '<b>베이스는 최소 5~7주.</b> 7일짜리 쉼은 베이스가 아니다.',
  '<b>제로선 "직전" 선취매는 절반(0.5R)까지만</b>, 손절선은 직전 눌림 저점. 나머지 절반은 돌파 확인 후.',
  '<b>추가 매수는 손절선이 가까운 자리에서만.</b> 같은 금액이라도 눌림에서 사면 R이 절반이 된다.',
  '<b>목표주가와 현재가의 괴리를 본다.</b> 주가가 목표가를 넘어선 종목은 애널리스트가 올려주지 않으면 쉬어간다. 2027년 전망이 2026년보다 낮은 종목(실적 정점 전망)은 뒤로 미룬다.',
  '<b>종목 비중 합계는 3~5R.</b> 손절선이 본전 위로 올라온 종목은 위험 계산에서 빼도 되지만, 신규 진입은 그 합계 안에서만.'
];

var DONTS = [
  '조정이 올 것 같다고 장중에 미리 파는 것. 규칙 밖의 매도는 나중에 "왜 팔았지"로 돌아온다.',
  '떨어진 김에 추가 매수하는 것. 비중을 줄이는 국면에서는 하지 않는다.',
  '1/3 판 뒤 더 올랐다고 다시 사는 것. 그 순간 규칙이 깨진다.',
  '매도선을 내리는 것. 선은 올리기만 한다.',
  '"실적이 좋으니까"로 매도선을 무시하는 것. 실적은 종목을 고를 때 쓰고, 팔 때는 가격만 본다.',
  '장중 가격으로 판단하는 것. 매도선은 전부 종가 기준이고, 장 마감 10분 전에 한 번만 본다.',
  '<b>뉴스 보고 장전·시초가에 사는 것.</b> 진입 신호는 전날 종가에서만 난다. 1면 기사는 이미 모두가 아는 재료라 시초가는 그날의 고점이 되기 쉽다 (10/8 한미약품: 허가 기사 다음 날 장전 매수 → 시초 −8% 손절). 재료가 좋아 보여도 종가가 돌파를 확인한 다음 날, 그것도 시초가 급등이면 눌림까지 기다린다.'
];

/* 변경 이력 — 대화에서 원칙이 바뀌거나 추가될 때마다 위에 한 줄씩 쌓습니다. */
var CHANGELOG = [
  ['2026-10-08', '가온전선 1R 시가(310,000) 전량 매도 — 10/7 신고가 후 장대 음봉으로 본전선 이탈. 평단 310,700 대비 −0.2%, 사실상 본전 청산. 재진입 조건: 종가 359,500 돌파.'],
  ['2026-10-08', '한미약품(에페 허가 기사) 장전 1R 매수 → 시초가 −8% 손절 (손실 약 0.08R). 전날 "551,000 종가 돌파 확인 후 0.5R" 계획을 어기고 뉴스 추격 + 분할 없이 1R. 금지 항목에 "뉴스 보고 장전·시초가 매수" 추가.'],
  ['2026-10-07', '매매: 컴투스 2R → 1R 축소(평단 37,838 유지) · 코스맥스 1R 신규 매수(평단 305,200, 초기 손절 264,000). 비중 합계 유지를 위해 축소 후 진입.'],
  ['2026-10-07', '본전선 전환 기준을 고점 +5% → +10% 로 변경. 검증(소부장 신고가 돌파 204건): +5% 단계 본전선은 승률 41%·중앙값 −0.9%, +10% 단계는 승률 60%·중앙값 +9.5%·최악 −14%. 티에스이는 고점 +12.8%라 본전선 유지, 삼성전기(+7.1%)·가온전선(+7.5%)은 초기 손절선으로 복귀.'],
  ['2026-10-07', '고점 −15% 선의 고점을 종가 최고가에서 수정 고가(장중 고가) 최고가로 변경하고, 진입일 이후 고점만 쓰도록 수정(진입 전 고점이 섞이던 문제). 시초가·장중에 찍은 고점도 매도선에 바로 반영.'],
  ['2026-10-06', '페이지를 스터디에서 관리자 탭으로 이동. 보유 종목·평단을 매매 복기 체결내역에서 자동 계산. 비중(R)·초기 손절가·메모 설정 추가. 신규 진입 종목은 고점 +5% 전까지 초기 손절가 적용.'],
  ['2026-10-06', '매매: KODEX 구리 전량 매도 · 컴투스 1R 추가 매수(합계 2R, 평단 37,838) · 삼성전기 1R 추가 매수(합계 2R, 평단 1,574,000) · 심텍·피에스케이홀딩스 시초가 +20% 도달 → 1/3 매도. 씨젠 0.5R(35,887) 보유 등록.'],
  ['2026-10-02', '매수 체크리스트 추가 (급등 뒤 돌파 · 무너진 주도주 박스 돌파 · 제로선 직전 선취매 통계). 가온전선 추가 매수 보류, 삼성전기 매수 보류 판단.'],
  ['2026-10-02', '분할 익절 규칙 채택: +20% 1/3, +40% 절반, 나머지 고점 −15%/본전. 193건 검증으로 전량 매도 규칙 대비 중앙값 +7%p.'],
  ['2026-10-01', '매도 원칙 첫 정리: 고점 −15% 또는 본전 이탈 전량 매도, 10일선은 경계선. 소부장 74종목 286건 백테스트.']
];

/* ---------- 유틸 ---------- */
var esc = function (s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); };
var fmt = function (v) { return Math.round(v).toLocaleString(); };
var pct = function (v, d) { return (v >= 0 ? '+' : '') + v.toFixed(d == null ? 1 : d) + '%'; };
var isoD = function (d) { return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10); };
function monthsBack(n) { var out = [], d = new Date(); for (var i = 0; i < n; i++) { out.push(d.toISOString().slice(0, 7)); d.setDate(1); d.setMonth(d.getMonth() - 1); } return out; }
function loadPq() {
  if (root.hyparquet) return Promise.resolve();
  return new Promise(function (ok, bad) { var s = document.createElement('script'); s.src = PQ_SRC; s.onload = ok; s.onerror = function () { bad(new Error('hyparquet 로드 실패')); }; document.head.appendChild(s); });
}
async function readPq(url, columns) {
  var res = await fetch(url); if (!res.ok) return [];
  return await root.hyparquet.parquetReadObjects({ file: await res.arrayBuffer(), columns: columns });
}
function getMeta() { try { var v = JSON.parse(localStorage.getItem(LS_KEY)); if (v && typeof v === 'object') return v; } catch (e) {} return {}; }
function setMeta(m) { try { localStorage.setItem(LS_KEY, JSON.stringify(m)); } catch (e) {} }

/* ---------- 체결내역 → 현재 보유 (평균단가 · 수량 · 이번 보유 중 매도 비율) ---------- */
function positionsFromRows(rows) {
  var pos = {};
  rows.forEach(function (r) {
    var p = pos[r.name] || (pos[r.name] = { q: 0, cost: 0, peakQ: 0, first: null, lastSell: null });
    if (r.side === 'B') { if (p.q === 0) { p.first = r.date; p.peakQ = 0; p.cost = 0; p.lastSell = null; } p.q += r.qty; p.cost += r.qty * r.price; p.peakQ = Math.max(p.peakQ, p.q); }
    else { if (p.q <= 0) return; var avg = p.cost / p.q; var q = Math.min(r.qty, p.q); p.q -= q; p.cost -= avg * q; p.lastSell = r.date; if (p.q <= 0) { p.q = 0; p.cost = 0; } }
  });
  var out = {};
  Object.keys(pos).forEach(function (n) { var p = pos[n]; if (p.q > 0) out[n] = { qty: p.q, avg: p.cost / p.q, soldFrac: p.peakQ ? 1 - p.q / p.peakQ : 0, first: p.first, lastSell: p.lastSell }; });
  return out;
}

/* ---------- 탭 ---------- */
function mount(opt) {
  var sb = opt.client, box = document.getElementById('rulesBox');
  var state = { loaded: false, px: null, hi: null, last: null, journalPos: null, journalInfo: '' };

  function staticHtml() {
    var h = '';
    h += '<div class="card"><h2>📐 매수·매도 원칙 <span class="cnt">이 계정만 볼 수 있습니다 · 대화에서 원칙이 바뀔 때마다 갱신</span></h2>' +
      '<div class="jnote">매도는 <b>종가 기준</b>으로만 판단한다. 평단 <b>+20%</b>에 1/3, <b>+40%</b>에 남은 것의 절반. 나머지는 <b>본전선과 최근 고점 −15% 중 높은 쪽</b> 아래로 종가가 가면 전량. 막 들어간 종목은 고점이 <b>+10%</b>를 넘기 전까지 <b>초기 손절가</b>. 10일선은 매도 신호가 아니라 <b>경계 신호</b>. 판 물량은 <b>신고가 돌파</b>에만 다시 산다.</div>';
    RULES.forEach(function (r, i) {
      h += '<div class="rrule"><div class="rn">' + (i + 1) + '</div><div><h3>' + r[0] + '</h3><p>' + r[1] + '</p>' + (r[2] ? '<div class="rwhy">' + r[2] + '</div>' : '') + '</div></div>';
    });
    h += '</div>';

    h += '<div class="card"><h2>📋 보유 종목 매도선 <span class="cnt" id="rHoldSub">불러오는 중…</span></h2>' +
      '<div class="twrap"><table><thead><tr><th class="l">종목</th><th>수량</th><th>평단</th><th>종가</th><th>수익률</th><th>+20%선</th><th>+40%선</th><th>본전선</th><th>고점−15%<br><span class="rsub">(진입 후 고가)</span></th><th>적용 매도선</th><th>여유</th><th>10일선</th><th>20일선</th><th>판단</th><th></th></tr></thead>' +
      '<tbody id="rHoldBody"><tr><td colspan="15" class="empty">불러오는 중…</td></tr></tbody></table></div>' +
      '<p class="muted" style="font-size:12.5px;margin-top:8px">판단: <span class="rtag sell">매도</span> 종가가 적용 매도선 아래 · <span class="rtag part">분할</span> +20% 또는 +40% 통과(다음 날 실행) · <span class="rtag near">주의</span> 매도선까지 5% 이내 · <span class="rtag hold">보유</span> 그 외. ' +
      '평단·수량·매도 비율은 <b>매매 복기에 저장된 체결내역</b>에서 자동 계산(체결내역에 없는 종목은 기본 설정값). 고점은 <b>진입일 이후 수정 고가(장중 고가)</b>의 최고가(진입일은 체결내역의 첫 매수일, 없으면 설정값·최근 60거래일). 적용 매도선: 고점이 평단 +10%를 넘긴 뒤에는 본전선과 고점 −15% 중 높은 쪽, 그 전에는 초기 손절가(없으면 −7%). 비중(R)·초기 손절가·메모는 "설정" 버튼으로 이 브라우저에 저장.</p>' +
      '<div class="ctl" style="margin-top:8px"><input type="text" id="rName" placeholder="종목명 (체결내역에 없는 종목 추가)"><input type="text" id="rCost" placeholder="평단" inputmode="numeric"><input type="text" id="rR" placeholder="R" inputmode="decimal" style="min-width:60px"><input type="text" id="rStop" placeholder="초기 손절가" inputmode="numeric"><button class="btn sub" id="rAdd">추가 / 수정</button><button class="btn sub" id="rReset">설정 초기화</button></div>' +
      '</div>';

    h += '<div class="card"><h2>🚦 사이클 경고 신호 <span class="cnt">둘 중 하나라도 켜지면 전체 절반 축소</span></h2><div class="rsig">' +
      '<div class="rbox"><h3>① 메모리 대형주 7/30 저점 이탈</h3><div class="v" id="rSigBig">확인 중…</div><div class="k" id="rSigBigK">삼성전자·SK하이닉스 종가가 2026-07-30 종가 아래로 내려가면 소부장 판정과 무관하게 전체 정리.</div></div>' +
      '<div class="rbox"><h3>② 소부장 신고가 종목 비율 40% 이상</h3><div class="v" id="rSigNh">확인 중…</div><div class="k" id="rSigNhK">이번 사이클 앞선 두 고점에서 이 비율이 정점을 찍고 2주~2개월 뒤 지수가 꺾여 −16%, −58% 빠졌다.</div></div>' +
      '<div class="rbox"><h3>③ 테스트 업종 목표주가 상향 폭 50% 초과</h3><div class="v" id="rSigTp">확인 중…</div><div class="k" id="rSigTpK">병목 업종에서 애널리스트가 앞다퉈 목표가를 올리기 시작하면 과열 시작. 신규 매수 중단 신호.</div></div>' +
      '</div><p class="muted" style="font-size:12.5px;margin-top:8px">②③은 <a href="/study/semi-cycle/" target="_blank" rel="noopener">반도체 사이클 계기판</a> 데이터를 그대로 읽는다.</p></div>';

    h += '<div class="card"><h2>🛒 매수 원칙 <span class="cnt">돌파라고 다 같은 돌파가 아니다</span></h2><ol class="jul" style="padding-left:22px">' + BUY_RULES.map(function (s) { return '<li>' + s + '</li>'; }).join('') + '</ol>' +
      '<h3 style="margin-top:16px">돌파 유형별 통계 (2024년 이후 전 종목)</h3><div class="twrap"><table><thead><tr><th class="l">돌파 유형</th><th>건수</th><th>40~60일 후 중앙값</th><th>승률</th><th>최대 하락 중앙값</th><th>−15% 이상 조정</th></tr></thead><tbody>' +
      BUY_STATS.map(function (r) { return '<tr class="' + r[6] + '"><td class="l">' + r[0] + '</td><td>' + r[1] + '</td><td>' + r[2] + '</td><td>' + r[3] + '</td><td>' + r[4] + '</td><td>' + r[5] + '</td></tr>'; }).join('') + '</tbody></table></div></div>';

    h += '<div class="card"><h2>🧪 왜 이 매도 규칙인가 <span class="cnt">+15% 수익 상태에서 규칙 시작, 193건, 진입가 기준 120거래일 결과</span></h2>' +
      '<div class="twrap"><table><thead><tr><th class="l">규칙</th><th>평균</th><th>중앙값</th><th>승률</th><th>최악</th><th>손실로 끝남</th><th>+30% 이상</th></tr></thead><tbody>' +
      BACKTEST.map(function (r) { return '<tr class="' + r[7] + '"><td class="l">' + r[0] + '</td><td>' + r[1] + '</td><td>' + r[2] + '</td><td>' + r[3] + '</td><td>' + r[4] + '</td><td>' + r[5] + '</td><td>' + r[6] + '</td></tr>'; }).join('') +
      '</tbody></table></div><p class="jp">그냥 보유가 평균은 가장 높지만 10건 중 3건은 수익을 전부 반납하고 손실로 끝났다. 채택한 규칙은 평균을 조금 내주는 대신 중앙값·승률을 올리고 최악을 −14%에서 자른다. 종목 하나가 +150% 가는 경우를 일부 포기하는 값이다.</p>' +
      '<p class="muted" style="font-size:12.5px">대상: 반도체 소부장 74종목, 2025-10~2026-07 신고가 돌파 중 60일 안에 +15% 도달한 건. 2026년 1~3월·4~5월 두 번의 고점 구간 포함. 수수료 0.3% 반영.</p></div>';

    h += '<div class="card"><h2>🚫 하지 말아야 할 것</h2><ul class="jul">' + DONTS.map(function (s) { return '<li>' + s + '</li>'; }).join('') + '</ul></div>';

    h += '<div class="card"><h2>🕘 변경 이력</h2><ul class="jul">' + CHANGELOG.map(function (c) { return '<li><b>' + c[0] + '</b> — ' + c[1] + '</li>'; }).join('') + '</ul></div>';
    return h;
  }

  async function loadPrices() {
    await loadPq();
    var S = {}, HI = {}, months = monthsBack(5);
    await Promise.all(months.map(async function (m) {
      var rows = []; try { rows = await readPq('/db/market/price/' + m + '.parquet', ['date', 'name', 'close']); } catch (e) {}
      rows.forEach(function (r) { if (r.close > 0) (S[r.name] || (S[r.name] = {}))[isoD(r.date)] = r.close; });
      var hs = []; try { hs = await readPq('/db/market/ohlc/' + m + '.parquet', ['date', 'name', 'high']); } catch (e) {}
      hs.forEach(function (r) { if (r.high > 0) (HI[r.name] || (HI[r.name] = {}))[isoD(r.date)] = r.high; });
    }));
    var out = {}, hi = {}, last = '';
    Object.keys(S).forEach(function (n) { out[n] = Object.keys(S[n]).sort().map(function (d) { return [d, S[n][d]]; }); var l = out[n][out[n].length - 1][0]; if (l > last) last = l; });
    Object.keys(HI).forEach(function (n) { hi[n] = Object.keys(HI[n]).sort().map(function (d) { return [d, HI[n][d]]; }); });
    state.px = out; state.hi = hi; state.last = last;
  }

  async function loadJournal() {
    if (!root.Journal || !sb) return;
    try {
      var r = await sb.from('trade_journal').select('raw,updated_at').maybeSingle();
      if (r && r.data && r.data.raw) {
        state.journalPos = positionsFromRows(Journal.parse(r.data.raw));
        state.journalInfo = '체결내역 ' + new Date(r.data.updated_at).toLocaleDateString('ko-KR') + ' 저장분 기준';
      } else state.journalInfo = '저장된 체결내역 없음 — 기본 설정값 사용';
    } catch (e) { state.journalInfo = '체결내역을 읽지 못함 — 기본 설정값 사용'; }
  }

  function holdings() {
    var meta = getMeta(), names = {};
    Object.keys(DEFAULT_META).forEach(function (n) { names[n] = 1; });
    Object.keys(meta).forEach(function (n) { if (!meta[n].removed) names[n] = 1; else delete names[n]; });
    Object.keys(DEFAULT_HIDE).forEach(function (n) { if (!(meta[n] && meta[n].removed === false)) delete names[n]; });
    if (state.journalPos) Object.keys(state.journalPos).forEach(function (n) { if (!(meta[n] && meta[n].removed) && !(DEFAULT_HIDE[n] && !(meta[n] && meta[n].removed === false))) names[n] = 1; });
    return Object.keys(names).map(function (n) {
      var d = DEFAULT_META[n] || {}, m = meta[n] || {}, j = state.journalPos ? state.journalPos[n] : null;
      return { name: n, cost: (j && j.avg) || m.cost || d.cost || 0, qty: j ? j.qty : null, soldFrac: j ? j.soldFrac : 0, fromJournal: !!j,
        since: (j && j.first) || m.since || d.since || null,
        r: m.r || d.r || 1, stop: m.stop || d.stop || 0, memo: (m.memo != null ? m.memo : d.memo) || '' };
    }).filter(function (h) { return h.cost > 0; });
  }

  function renderHold() {
    var body = document.getElementById('rHoldBody'), sub = document.getElementById('rHoldSub');
    var H = holdings();
    if (!state.px) { body.innerHTML = '<tr><td colspan="15" class="empty">가격 데이터를 불러오지 못했습니다</td></tr>'; return; }
    var totR = 0, h = '';
    H.forEach(function (x) {
      var a = state.px[x.name];
      var memo = x.memo || '';
      // 분할 진행: 체결내역의 매도 비율이 우선, 없으면 메모로 판단
      var sold20 = x.soldFrac >= 0.3 || /1\/3|20%/.test(memo), sold40 = x.soldFrac >= 0.55 || /절반|40%/.test(memo);
      var remain = sold40 ? 1 / 3 : sold20 ? 2 / 3 : 1; totR += x.r * remain;
      var label = '<b>' + esc(x.name) + '</b> <span class="rR">' + x.r + 'R</span>' + (x.since ? ' <span class="rsub">' + x.since.slice(5) + '~</span>' : '') + (x.fromJournal ? '' : ' <span class="rman" title="체결내역에 없어 기본 설정값 사용">설정값</span>') +
        (x.soldFrac > 0.05 ? '<br><span class="rsub">보유 중 ' + Math.round(x.soldFrac * 100) + '% 매도</span>' : '') + (memo ? '<br><span class="rsub">' + esc(memo) + '</span>' : '');
      var btns = '<td><button class="chip" data-set="' + esc(x.name) + '">설정</button> <button class="chip" data-del="' + esc(x.name) + '">숨김</button></td>';
      if (!a || a.length < 20) { h += '<tr><td class="l">' + label + '</td><td>' + (x.qty || '–') + '</td><td>' + fmt(x.cost) + '</td><td colspan="11" style="text-align:left;color:#9099a6">가격 DB에 없는 종목명</td>' + btns + '</tr>'; return; }
      var c = a.map(function (p) { return p[1]; }), px = c[c.length - 1], ret = (px / x.cost - 1) * 100;
      // 고점: 수정 고가(ohlc) 기준. 진입일(since)을 알면 그 날 이후, 모르면 최근 60거래일. 고가 DB가 없는 종목은 종가
      var src = state.hi && state.hi[x.name] && state.hi[x.name].length ? state.hi[x.name] : a, peakSrc = (src === a) ? '종가' : '고가';
      var win = x.since ? src.filter(function (p) { return p[0] >= x.since; }) : src.slice(-MAX_DAYS_PEAK);
      if (!win.length) win = src.slice(-MAX_DAYS_PEAK);
      var peak = -1, peakD = ''; win.forEach(function (p) { if (p[1] > peak) { peak = p[1]; peakD = p[0]; } });
      var l15 = peak * (1 - TRAIL), be = x.cost;
      var armed = peak >= x.cost * (1 + ARM_PCT), init = x.stop > 0 ? x.stop : x.cost * (1 - INIT_STOP);
      var line = armed ? Math.max(l15, be) : init, lineLbl = !armed ? '초기 손절' : (line === be ? '본전' : '고점−15%');
      var ma10 = c.slice(-10).reduce(function (s, v) { return s + v; }, 0) / 10, ma20 = c.slice(-20).reduce(function (s, v) { return s + v; }, 0) / 20;
      var room = (line / px - 1) * 100, tag, cls;
      if (px < line) { tag = '매도'; cls = 'sell'; }
      else if (ret >= 40 && !sold40) { tag = '+40% 분할'; cls = 'part'; }
      else if (ret >= 20 && !sold20) { tag = '+20% 분할'; cls = 'part'; }
      else if (room >= -5) { tag = '주의'; cls = 'near'; }
      else { tag = '보유'; cls = 'hold'; }
      h += '<tr><td class="l">' + label + '</td><td>' + (x.qty != null ? fmt(x.qty) : '–') + '</td><td>' + fmt(x.cost) + '</td><td>' + fmt(px) + '</td>' +
        '<td class="' + (ret >= 0 ? 'jup' : 'jdn') + '">' + pct(ret) + '</td><td>' + fmt(x.cost * 1.2) + '</td><td>' + fmt(x.cost * 1.4) + '</td><td>' + fmt(be) + '</td><td>' + fmt(l15) + '<br><span class="rsub">' + peakSrc + ' ' + fmt(peak) + ' · ' + peakD.slice(5) + '</span></td>' +
        '<td><b>' + fmt(line) + '</b><br><span class="rsub">' + lineLbl + '</span></td><td class="' + (room > -5 ? 'rwarn' : '') + '">' + pct(room) + '</td>' +
        '<td>' + fmt(ma10) + '<br><span class="rsub' + (px < ma10 ? ' rwarn' : '') + '">' + (px < ma10 ? '아래 · 추가매수 금지' : '위') + '</span></td><td>' + fmt(ma20) + '</td>' +
        '<td><span class="rtag ' + cls + '">' + tag + '</span></td>' + btns + '</tr>';
    });
    body.innerHTML = h || '<tr><td colspan="15" class="empty">보유 종목이 없습니다</td></tr>';
    sub.textContent = state.last + ' 종가 기준 · ' + state.journalInfo + ' · ' + H.length + '종목 · 남은 비중 약 ' + totR.toFixed(1) + 'R' + (totR > 5 ? ' (기준 3~5R 초과)' : '');
    body.querySelectorAll('[data-set]').forEach(function (b) { b.onclick = function () { editMeta(b.dataset.set); }; });
    body.querySelectorAll('[data-del]').forEach(function (b) { b.onclick = function () { var m = getMeta(); if (!confirm(b.dataset.del + ' 을(를) 표에서 숨길까요? (체결내역은 그대로)')) return; m[b.dataset.del] = Object.assign({}, m[b.dataset.del] || {}, { removed: true }); setMeta(m); renderHold(); }; });
  }

  function editMeta(name) {
    var m = getMeta(), cur = Object.assign({}, DEFAULT_META[name] || {}, m[name] || {});
    var r = prompt(name + ' 비중 (R)', cur.r || 1); if (r === null) return;
    var stop = prompt(name + ' 초기 손절가 (없으면 비움)', cur.stop || ''); if (stop === null) return;
    var since = prompt(name + ' 진입일 (YYYY-MM-DD, 체결내역이 있으면 비워도 됨)', cur.since || ''); if (since === null) return;
    var memo = prompt(name + ' 메모 (예: 1/3 매도, 절반 매도)', cur.memo || ''); if (memo === null) return;
    m[name] = Object.assign({}, m[name] || {}, { r: Number(r) || 1, stop: Number(String(stop).replace(/[^0-9.]/g, '')) || 0, since: /^\d{4}-\d{2}-\d{2}$/.test(since.trim()) ? since.trim() : '', memo: memo.trim(), removed: false });
    setMeta(m); renderHold();
  }

  function renderSignals() {
    var set = function (id, v, cls) { var el = document.getElementById(id); el.textContent = v; el.className = 'v ' + cls; };
    var rows = [];
    ['삼성전자', 'SK하이닉스'].forEach(function (n) {
      var a = state.px && state.px[n]; if (!a) return;
      var low = a.filter(function (p) { return p[0] === BIG_LOW_DATE; })[0], px = a[a.length - 1][1];
      if (low) rows.push([n, px, low[1], (px / low[1] - 1) * 100]);
    });
    if (rows.length) {
      var broke = rows.some(function (r) { return r[1] < r[2]; });
      set('rSigBig', broke ? '🔴 이탈 — 전체 정리' : '🟢 유지', broke ? 'bad' : 'ok');
      document.getElementById('rSigBigK').textContent = rows.map(function (r) { return r[0] + ' ' + fmt(r[1]) + ' (저점 ' + fmt(r[2]) + ' 대비 ' + pct(r[3]) + ')'; }).join(' · ');
    } else set('rSigBig', '데이터 없음', 'warn');
    fetch('/study/semi-cycle/data.json').then(function (r) { return r.json(); }).then(function (d) {
      var nh = d.sobu && d.sobu.signals ? d.sobu.signals.nh : null;
      if (nh != null) { set('rSigNh', (nh >= 40 ? '🔴 ' : nh >= 25 ? '🟡 ' : '🟢 ') + nh.toFixed(0) + '%', nh >= 40 ? 'bad' : nh >= 25 ? 'warn' : 'ok'); document.getElementById('rSigNhK').textContent = d.price_last + ' 기준 · 40% 이상 과열 · 15% 미만 초입'; }
      var t = (d.segments || []).filter(function (s) { return s.key === 'test' || /테스트/.test(s.label); })[0];
      if (t && t.signals) { var tp = t.signals.tp; set('rSigTp', (tp > 50 ? '🔴 ' : tp > 25 ? '🟡 ' : '🟢 ') + (tp >= 0 ? '+' : '') + tp.toFixed(0) + '%', tp > 50 ? 'bad' : tp > 25 ? 'warn' : 'ok'); document.getElementById('rSigTpK').textContent = d.price_last + ' 기준 · 목표주가 괴리 ' + (t.signals.gap >= 0 ? '+' : '') + t.signals.gap.toFixed(0) + '% · 신고가 비율 ' + t.signals.nh.toFixed(0) + '% · 단계 ' + (t.signals.hot >= 2 ? '과열' : t.signals.hot === 1 ? '진행' : '초입'); }
    }).catch(function () { set('rSigNh', '데이터 없음', 'warn'); set('rSigTp', '데이터 없음', 'warn'); });
  }

  function wire() {
    document.getElementById('rAdd').onclick = function () {
      var name = document.getElementById('rName').value.trim(), cost = Number(document.getElementById('rCost').value.replace(/[^0-9.]/g, ''));
      var r = Number(document.getElementById('rR').value) || 0, stop = Number(document.getElementById('rStop').value.replace(/[^0-9.]/g, '')) || 0;
      if (!name || !(cost > 0)) { alert('종목명과 평단을 입력하세요'); return; }
      var m = getMeta(); m[name] = Object.assign({}, m[name] || {}, { cost: cost, r: r || (m[name] && m[name].r) || (DEFAULT_META[name] || {}).r || 1, stop: stop || (m[name] && m[name].stop) || 0, removed: false });
      setMeta(m); ['rName', 'rCost', 'rR', 'rStop'].forEach(function (id) { document.getElementById(id).value = ''; }); renderHold();
    };
    document.getElementById('rReset').onclick = function () { if (!confirm('이 브라우저에 저장한 비중·손절가·메모·숨김 설정을 모두 지우고 기본값으로 되돌릴까요?')) return; setMeta({}); renderHold(); };
  }

  async function load() {
    box.innerHTML = staticHtml(); wire();
    await Promise.all([loadPrices().catch(function () {}), loadJournal()]);
    renderHold(); renderSignals();
  }

  return { open: function () { if (!state.loaded) { state.loaded = true; load(); } }, refresh: function () { state.loaded = false; } };
}

var api = { mount: mount, positionsFromRows: positionsFromRows, DEFAULT_META: DEFAULT_META, CHANGELOG: CHANGELOG };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
else root.Rules = api;
})(typeof window !== 'undefined' ? window : globalThis);
