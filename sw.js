// 가좌버핏 뉴스 사이트 전체 서비스워커 (scope: /)
// 전략: 네트워크 우선 + 캐시 폴백 — 온라인이면 항상 최신, 오프라인이면 마지막으로 본 페이지·데이터
const CACHE = 'gjbuffet-v1';
const SHELL = ['/', '/index.html'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  if (new URL(req.url).origin !== location.origin) return;  // gtag 등 외부 요청은 관여 안 함
  e.respondWith(
    fetch(req).then(resp => {
      if (resp.ok) {
        const copy = resp.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
      }
      return resp;
    }).catch(() =>
      caches.match(req).then(m =>
        m || (req.mode === 'navigate' ? caches.match('/index.html') : Response.error()))
    )
  );
});
