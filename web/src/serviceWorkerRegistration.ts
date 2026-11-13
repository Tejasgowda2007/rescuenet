/**
 * Service Worker Registration for RescueNet FieldMesh.
 * 
 * Manages service worker lifecycle, offline readiness detection,
 * and seamless background updates for Android PWA installation.
 */

type Config = {
  onSuccess?: (registration: ServiceWorkerRegistration) => void;
  onUpdate?: (registration: ServiceWorkerRegistration) => void;
};

export function register(config?: Config) {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      // Use relative sw.js to support subpaths or root
      const swUrl = './sw.js';

      navigator.serviceWorker
        .register(swUrl)
        .then((registration) => {
          console.log('[RescueNet PWA] Service Worker registered with scope:', registration.scope);

          registration.onupdatefound = () => {
            const installingWorker = registration.installing;
            if (installingWorker == null) {
              return;
            }
            installingWorker.onstatechange = () => {
              if (installingWorker.state === 'installed') {
                if (navigator.serviceWorker.controller) {
                  // Updated content available
                  console.log('[RescueNet PWA] New content is available; please refresh.');
                  if (config && config.onUpdate) {
                    config.onUpdate(registration);
                  }
                } else {
                  // Content cached for offline use
                  console.log('[RescueNet PWA] Content is cached for offline use.');
                  if (config && config.onSuccess) {
                    config.onSuccess(registration);
                  }
                }
              }
            };
          };
        })
        .catch((error) => {
          console.error('[RescueNet PWA] Service worker registration error:', error);
        });
    });
  }
}

export function unregister() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready
      .then((registration) => {
        registration.unregister();
      })
      .catch((error) => {
        console.error(error.message);
      });
  }
}
