// (구) ETF 전용 서비스워커 — 사이트 전체 워커(/sw.js)로 통합되어 자체 해제됩니다.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.delete('etf-app-v1')
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll())
      .then(cs => cs.forEach(c => c.navigate(c.url)))  // 새 워커가 넘겨받도록 리로드
  );
});
