// ETF 검색기 서비스워커
// 전략: 네트워크 우선 + 캐시 폴백 — 온라인이면 항상 최신, 오프라인이면 마지막으로 본 데이터
// (Parquet 데이터 파일 /db/... 요청도 이 페이지에서 발생하므로 함께 캐시됨)
const CACHE = 'etf-app-v1';
const SHELL = [
  '/tools/etf/',
  '/tools/etf/index.html',
  '/tools/etf/hyparquet.min.js',
  '/tools/etf/manifest.webmanifest',
  '/tools/etf/icon-192.png'
];

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
        m || (req.mode === 'navigate' ? caches.match('/tools/etf/index.html') : Response.error()))
    )
  );
});
