// ===== 가좌버핏 회원 로그인 (Supabase Auth · 구글 로그인) =====
// 사용법: 아래 세 줄을 순서대로 넣고, 버튼을 놓을 자리에 Auth.mount(엘리먼트) 호출
//   <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"></script>
//   <script src="/assets/auth-config.js"></script>
//   <script src="/assets/auth.js"></script>
// 제공: Auth.user(로그인 정보 또는 null) · Auth.ready(초기 확인 완료 Promise)
//       Auth.login() · Auth.logout() · Auth.onChange(fn) · Auth.mount(el)
(function () {
  'use strict';

  var cfg = window.GJ_AUTH || {};
  var configured = !!(cfg.url && cfg.anonKey && /^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(cfg.url));
  var CONSENT_KEY = 'gj.auth.consent.v1';
  var listeners = [];
  var mounts = [];
  var client = null;
  var readyDone = false;

  var Auth = {
    configured: configured,
    user: null,
    role: null,          // 'master' | 'admin' | 'sub' | 'member' | null (profiles 테이블에서)
    roleReady: null,     // 역할 조회 완료 Promise
    client: null,        // supabase-js 클라이언트 (다른 페이지에서 DB 호출용)
    ready: null,
    onChange: function (fn) { listeners.push(fn); },
    login: login,
    logout: logout,
    mount: mount,
    isStaff: function () { return ['master', 'admin', 'sub'].indexOf(Auth.role) >= 0; },
    logView: logView
  };
  window.Auth = Auth;

  /* ---------- 스타일 (칩 + 동의창) ---------- */
  var css = document.createElement('style');
  css.textContent =
    '.gj-auth{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-family:inherit}' +
    '.gj-auth .gj-btn{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:999px;border:none;cursor:pointer;' +
      'font:inherit;font-size:13px;font-weight:700;background:linear-gradient(135deg,#1a3a6c,#2a5ca8);color:#fff;white-space:nowrap}' +
    '.gj-auth .gj-btn:disabled{opacity:.55;cursor:default}' +
    '.gj-auth .gj-user{display:inline-flex;align-items:center;gap:7px;padding:4px 10px 4px 4px;border-radius:999px;background:#eef1f6;color:#33415c;max-width:220px}' +
    '.gj-auth .gj-user img{width:24px;height:24px;border-radius:50%;background:#dfe3e8;flex:0 0 24px}' +
    '.gj-auth .gj-user .gj-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}' +
    '.gj-auth .gj-out{background:none;border:none;color:#6b7280;cursor:pointer;font:inherit;font-size:12px;padding:4px 2px;white-space:nowrap}' +
    '.gj-auth .gj-out:hover{color:#1a3a6c;text-decoration:underline}' +
    '.gj-auth .gj-off{font-size:12px;color:#9099a6;white-space:nowrap}' +
    '.gj-modal{position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px}' +
    '.gj-modal .gj-box{background:#fff;border-radius:14px;max-width:400px;width:100%;padding:22px 22px 18px;box-shadow:0 20px 60px rgba(0,0,0,.25);font-family:inherit;color:#1a1a1a}' +
    '.gj-modal h3{margin:0 0 8px;font-size:17px;color:#1a3a6c}' +
    '.gj-modal p{margin:0 0 10px;font-size:13.5px;line-height:1.65;color:#374151}' +
    '.gj-modal ul{margin:0 0 12px 18px;padding:0;font-size:13px;color:#4b5563;line-height:1.6}' +
    '.gj-modal .gj-row{display:flex;gap:8px;margin-top:14px}' +
    '.gj-modal .gj-row button{flex:1;padding:11px;border-radius:9px;border:none;font:inherit;font-size:14px;font-weight:700;cursor:pointer}' +
    '.gj-modal .gj-go{background:linear-gradient(135deg,#1a3a6c,#2a5ca8);color:#fff}' +
    '.gj-modal .gj-no{background:#eef1f6;color:#33415c}' +
    '.gj-modal a{color:#2a5ca8}';
  document.head.appendChild(css);

  /* ---------- 초기화 ---------- */
  function toUser(u) {
    if (!u) return null;
    var m = u.user_metadata || {};
    return {
      id: u.id,
      email: u.email || '',
      name: m.full_name || m.name || (u.email ? u.email.split('@')[0] : '회원'),
      avatar: m.avatar_url || m.picture || ''
    };
  }

  function emit(prevId) {
    var curId = Auth.user ? Auth.user.id : null;
    if (prevId === curId) return;
    listeners.forEach(function (fn) { try { fn(Auth.user); } catch (e) { console.error(e); } });
  }

  function stripAuthParams() {
    try {
      var u = new URL(location.href);
      var changed = false;
      ['code', 'error', 'error_code', 'error_description'].forEach(function (k) {
        if (u.searchParams.has(k)) { u.searchParams.delete(k); changed = true; }
      });
      if (u.hash && /access_token|refresh_token|error/.test(u.hash)) { u.hash = ''; changed = true; }
      if (changed) history.replaceState(history.state, '', u.pathname + (u.search || '') + (u.hash || ''));
    } catch (e) {}
  }

  if (!configured || !window.supabase || !window.supabase.createClient) {
    if (!configured) console.info('[Auth] 로그인 설정 없음 — assets/auth-config.js 에 url/anonKey 를 채우면 켜집니다.');
    else console.warn('[Auth] supabase-js 가 로드되지 않았습니다.');
    Auth.configured = false;
    Auth.ready = Promise.resolve(null);
    readyDone = true;
  } else {
    client = window.supabase.createClient(cfg.url, cfg.anonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: 'pkce' }
    });
    Auth.client = client;

    // 구글에서 돌아왔는데 실패한 경우: Supabase 가 주소(쿼리 또는 #해시)에 error_description 을 실어 보냄 → 화면에 그대로 보여줌
    (function () {
      var q = new URLSearchParams(location.search);
      var h = new URLSearchParams((location.hash || '').replace(/^#/, ''));
      var desc = q.get('error_description') || h.get('error_description');
      var code = q.get('error_code') || h.get('error_code') || q.get('error') || h.get('error');
      if (!desc && !code) return;
      var msg = decodeURIComponent(String(desc || code).replace(/\+/g, ' '));
      console.warn('[Auth] 로그인 실패:', code, msg);
      setTimeout(function () {
        alert('로그인에 실패했습니다.\n\n서버 메시지: ' + msg + (code ? '\n코드: ' + code : '') +
          '\n\n이 문구를 그대로 운영자에게 알려주세요.');
      }, 300);
    })();

    Auth.ready = client.auth.getSession().then(function (r) {
      var prev = Auth.user ? Auth.user.id : null;
      Auth.user = toUser(r && r.data && r.data.session ? r.data.session.user : null);
      readyDone = true;
      stripAuthParams();
      renderAll();
      Auth.roleReady = fetchRole();
      emit(prev);
      return Auth.user;
    }).catch(function (e) {
      console.warn('[Auth] 세션 확인 실패', e);
      readyDone = true;
      renderAll();
      return null;
    });

    client.auth.onAuthStateChange(function (event, session) {
      var prev = Auth.user ? Auth.user.id : null;
      Auth.user = toUser(session ? session.user : null);
      if (!readyDone) return;          // 초기 확인은 위 getSession 에서 한 번만 알림
      stripAuthParams();
      renderAll();
      if (prev !== (Auth.user ? Auth.user.id : null)) Auth.roleReady = fetchRole();
      emit(prev);
    });
  }

  /* ---------- 역할(관리자 여부) 조회 ---------- */
  function fetchRole() {
    Auth.role = null;
    if (!client || !Auth.user) { renderAll(); return Promise.resolve(null); }
    return client.from('profiles').select('role').eq('id', Auth.user.id).maybeSingle()
      .then(function (r) {
        Auth.role = (r && r.data && r.data.role) || 'member';
        renderAll();
        return Auth.role;
      })
      .catch(function () { Auth.role = 'member'; renderAll(); return Auth.role; });
  }

  /* ---------- 종목 조회 기록 (회원은 user_id, 비회원은 브라우저 식별자 anon_id · 같은 화면 5분 내 중복은 한 번만) ---------- */
  var lastView = { key: '', at: 0 };
  function anonId() {   // 좋아요 시스템과 같은 식별자(gjb_fp) 재사용 — 개인을 알아낼 수 없는 무작위 값
    var fp = null;
    try { fp = localStorage.getItem('gjb_fp'); } catch (e) {}
    if (!fp) {
      fp = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : ('fp_' + Date.now() + '_' + Math.random().toString(36).slice(2));
      try { localStorage.setItem('gjb_fp', fp); } catch (e) {}
    }
    return fp;
  }
  function logView(type, name, code, baseDate) {
    if (!client || !name) return;
    var key = type + '|' + name + '|' + (baseDate || '') + '|' + (Auth.user ? Auth.user.id : 'g');
    var now = Date.now();
    if (key === lastView.key && now - lastView.at < 5 * 60 * 1000) return;
    lastView = { key: key, at: now };
    var row = { view_type: type, name: name, code: code || null, base_date: baseDate || null };
    if (Auth.user) row.user_id = Auth.user.id; else { row.user_id = null; row.anon_id = anonId(); }
    client.from('stock_views').insert(row)
      .then(function (r) { if (r && r.error) console.warn('[Auth] 조회 기록 실패', r.error.message); });
  }

  /* ---------- 로그인 / 로그아웃 ---------- */
  function login() {
    if (!Auth.configured) {
      alert('로그인 기능을 준비 중입니다. 조금만 기다려 주세요.');
      return Promise.resolve(false);
    }
    var agreed = false;
    try { agreed = localStorage.getItem(CONSENT_KEY) === 'y'; } catch (e) {}
    var go = function () {
      try { localStorage.setItem(CONSENT_KEY, 'y'); } catch (e) {}
      var back = location.href.split('#')[0];
      return client.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: back, queryParams: { prompt: 'select_account' } }
      }).then(function (r) {
        if (r && r.error) { alert('로그인 창을 열지 못했습니다: ' + r.error.message); return false; }
        return true;
      });
    };
    return agreed ? go() : consent().then(function (ok) { return ok ? go() : false; });
  }

  function logout() {
    if (!client) return Promise.resolve();
    return client.auth.signOut().catch(function (e) { console.warn('[Auth] 로그아웃 실패', e); });
  }

  /* ---------- 동의창 (첫 로그인 때 한 번) ---------- */
  function consent() {
    return new Promise(function (resolve) {
      var wrap = document.createElement('div');
      wrap.className = 'gj-modal';
      wrap.innerHTML =
        '<div class="gj-box" role="dialog" aria-modal="true">' +
        '<h3>가좌버핏 회원으로 계속하기</h3>' +
        '<p>구글 계정으로 로그인하면 아래 정보를 <b>회원 식별 목적으로만</b> 보관합니다.</p>' +
        '<ul><li>이메일 주소</li><li>이름, 프로필 사진 (구글에 등록된 것)</li></ul>' +
        '<p>비밀번호는 저희가 받지 않으며, 언제든 탈퇴(삭제)를 요청할 수 있습니다. ' +
        '자세한 내용은 <a href="/privacy/" target="_blank" rel="noopener">개인정보 안내</a>를 봐 주세요.</p>' +
        '<div class="gj-row"><button class="gj-no" type="button">취소</button>' +
        '<button class="gj-go" type="button">동의하고 구글로 계속</button></div></div>';
      document.body.appendChild(wrap);
      var done = function (ok) { wrap.remove(); resolve(ok); };
      wrap.querySelector('.gj-no').onclick = function () { done(false); };
      wrap.querySelector('.gj-go').onclick = function () { done(true); };
      wrap.addEventListener('click', function (e) { if (e.target === wrap) done(false); });
    });
  }

  /* ---------- 버튼/칩 ---------- */
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  function render(el) {
    if (!el) return;
    el.classList.add('gj-auth');
    if (!Auth.configured) {          // 설정 전에는 방문자에게 아무것도 보이지 않음
      el.innerHTML = '';
      return;
    }
    if (!readyDone) {
      el.innerHTML = '<button class="gj-btn" type="button" disabled>확인 중…</button>';
      return;
    }
    if (Auth.user) {
      var u = Auth.user;
      el.innerHTML =
        '<span class="gj-user" title="' + esc(u.email) + '">' +
          (u.avatar ? '<img src="' + esc(u.avatar) + '" alt="" referrerpolicy="no-referrer">' : '<span style="width:24px;height:24px;border-radius:50%;background:#c9d6e8;display:inline-block"></span>') +
          '<span class="gj-name">' + esc(u.name) + '</span></span>' +
        (Auth.isStaff() && location.pathname.indexOf('/admin/') !== 0
          ? '<a class="gj-out" href="/admin/" style="text-decoration:none">&#9881; 관리자</a>' : '') +
        '<button class="gj-out" type="button">로그아웃</button>';
      el.querySelector('.gj-out').onclick = function () { logout(); };
    } else {
      el.innerHTML = '<button class="gj-btn" type="button">&#128100; 로그인</button>';
      el.querySelector('.gj-btn').onclick = function () { login(); };
    }
  }

  function renderAll() { mounts.forEach(render); }

  function mount(el) {
    if (!el || mounts.indexOf(el) >= 0) return;
    mounts.push(el);
    render(el);
  }
})();
