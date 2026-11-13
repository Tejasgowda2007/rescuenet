import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import * as serviceWorkerRegistration from './serviceWorkerRegistration';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Register Service Worker to enable offline PWA functionality on Android
serviceWorkerRegistration.register({
  onSuccess: () => console.log('[RescueNet] App is ready for offline operation.'),
  onUpdate: () => console.log('[RescueNet] New version cached; refresh to update.'),
});
