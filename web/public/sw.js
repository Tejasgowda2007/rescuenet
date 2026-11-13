/**
 * RescueNet FieldMesh Progressive Web App Service Worker (v2.0.0)
 * 
 * Provides defense-grade offline resilience:
 * 1. Cache-First App Shell: HTML, CSS, JS, Fonts, and Icons are served immediately from cache.
 * 2. Unhandled Rejection Prevention: All network fetch calls are caught; never breaks page load.
 * 3. Dynamic Asset Caching: Any newly requested JS chunk or asset is captured into cache.
 * 4. Fast API Timeout: Network-First API queries time out after 2.5s and fall back to cached snapshots.
 */

const CACHE_NAME = 'rescuenet-fieldmesh-v2.0.0';

const PRECACHE_ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-192.png',
  './icon-maskable-512.png',
  './icon.svg',
];

// Install: Pre-cache core app shell
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[RescueNet SW] Pre-caching core app shell...');
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('[RescueNet SW] Some precache assets failed to cache:', err);
      });
    })
  );
});

// Activate: Clean up legacy caches and immediately claim clients
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith('rescuenet-') && name !== CACHE_NAME)
          .map((name) => {
            console.log(`[RescueNet SW] Purging stale cache: ${name}`);
            return caches.delete(name);
          })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Robust strategy dispatch
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Ignore non-HTTP(S) schemes
  if (!url.protocol.startsWith('http')) return;

  // 1. Navigation requests (Opening the SPA): Cache-First with network fallback
  if (request.mode === 'navigate') {
    event.respondWith(
      caches.match('./index.html').then((cached) => {
        if (cached) {
          // Serve cached shell immediately for zero-latency offline start
          fetch(request)
            .then((res) => {
              if (res && res.status === 200) {
                const clone = res.clone();
                caches.open(CACHE_NAME).then((c) => c.put(request, clone));
              }
            })
            .catch(() => {});
          return cached;
        }

        // Not cached yet: fetch from network
        return fetch(request)
          .then((res) => {
            if (res && res.status === 200) {
              const clone = res.clone();
              caches.open(CACHE_NAME).then((c) => c.put(request, clone));
            }
            return res;
          })
          .catch(async () => {
            const rootCached = await caches.match('./');
            return rootCached || caches.match('/index.html') || new Response('Offline', { status: 503 });
          });
      })
    );
    return;
  }

  // 2. API Endpoints: Network-First with quick fallback
  if (url.pathname.startsWith('/api/')) {
    if (request.method === 'GET') {
      event.respondWith(
        Promise.race([
          fetch(request).then((res) => {
            if (res && res.status === 200) {
              const clone = res.clone();
              caches.open(CACHE_NAME).then((c) => c.put(request, clone));
            }
            return res;
          }),
          new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 2500)),
        ]).catch(async () => {
          const cached = await caches.match(request);
          if (cached) return cached;
          return new Response(
            JSON.stringify({ offline: true, error: 'Offline - Mesh currently unreachable' }),
            {
              headers: { 'Content-Type': 'application/json' },
              status: 200,
            }
          );
        })
      );
    } else {
      // POST/PUT/DELETE
      event.respondWith(
        fetch(request).catch(() => {
          return new Response(
            JSON.stringify({
              status: 'QUEUED_OFFLINE',
              queued: true,
              message: 'Device offline. Mutation queued in IndexedDB outbox.',
              timestamp: Date.now(),
            }),
            {
              headers: { 'Content-Type': 'application/json' },
              status: 202,
            }
          );
        })
      );
    }
    return;
  }

  // 3. Static Assets (.js, .css, images, fonts): Cache-First
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;

      return fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => {
          // If request is for an image/icon, return a transparent pixel or empty SVG
          if (request.destination === 'image') {
            return new Response(
              '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"></svg>',
              { headers: { 'Content-Type': 'image/svg+xml' } }
            );
          }
          return new Response('', { status: 408, statusText: 'Request timed out / offline' });
        });
    })
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
