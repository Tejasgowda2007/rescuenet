import React, { useState, useEffect } from 'react';
import { Wifi, WifiOff, RefreshCw, Smartphone, CheckCircle, Database } from 'lucide-react';
import { offlineStorage } from '../services/offlineStorage';
import { useAuth } from '../context/AuthContext';

interface NetworkStatusBarProps {
  wsConnected?: boolean;
}

export const NetworkStatusBar: React.FC<NetworkStatusBarProps> = ({ wsConnected = false }) => {
  const { apiFetch } = useAuth();
  const [isBrowserOnline, setIsBrowserOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [isStandalone, setIsStandalone] = useState<boolean>(false);

  useEffect(() => {
    // Check if running as installed standalone PWA
    const checkStandalone = () => {
      const isStandaloneMode =
        window.matchMedia('(display-mode: standalone)').matches ||
        (window.navigator as any).standalone === true;
      setIsStandalone(isStandaloneMode);
    };
    checkStandalone();

    // Listen for online / offline events
    const handleOnline = () => {
      setIsBrowserOnline(true);
      // Automatically attempt to flush outbox when connection restores
      offlineStorage.flushOutbox(apiFetch).then(({ synced }) => {
        if (synced > 0) {
          setSyncMessage(`Mesh restored: ${synced} offline action(s) synced.`);
          setTimeout(() => setSyncMessage(null), 4000);
        }
      });
    };

    const handleOffline = () => {
      setIsBrowserOnline(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Subscribe to IndexedDB outbox count
    const unsubscribe = offlineStorage.subscribe((count) => {
      setPendingCount(count);
    });

    // PWA install prompt handler
    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
      console.log('[RescueNet PWA] Captured beforeinstallprompt event for Android installation');
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      unsubscribe();
    };
  }, [apiFetch]);

  // Handle manual sync click
  const handleManualSync = async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    setSyncMessage(null);
    try {
      const { synced, failed } = await offlineStorage.flushOutbox(apiFetch);
      if (synced > 0 && failed === 0) {
        setSyncMessage(`Successfully synced ${synced} offline change(s) to mesh.`);
      } else if (synced > 0 && failed > 0) {
        setSyncMessage(`Synced ${synced} item(s), ${failed} failed (peer may be partitioned).`);
      } else if (failed > 0) {
        setSyncMessage(`Sync failed (${failed} item(s)). Mesh node currently unreachable.`);
      } else {
        setSyncMessage('Mesh up-to-date. Zero pending offline changes.');
      }
    } catch {
      setSyncMessage('Sync error: Mesh host unreachable.');
    } finally {
      setIsSyncing(false);
      setTimeout(() => setSyncMessage(null), 5000);
    }
  };

  // Handle PWA installation trigger
  const handleInstallClick = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    console.log(`[RescueNet PWA] User install response: ${outcome}`);
    setDeferredPrompt(null);
  };

  const isActuallyOnline = isBrowserOnline && wsConnected;

  return (
    <div
      role="region"
      aria-label="Network and Offline Status"
      className={`border-b transition-colors px-4 sm:px-6 py-2 text-xs flex flex-wrap items-center justify-between gap-3 ${
        isActuallyOnline
          ? 'bg-emerald-50/80 border-emerald-200 text-emerald-900'
          : 'bg-amber-50 border-amber-300 text-amber-950'
      }`}
    >
      {/* Left: Visible Online / Offline Status Indicator */}
      <div className="flex items-center gap-2.5">
        {isActuallyOnline ? (
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-600"></span>
            </span>
            <div className="flex items-center gap-1.5 font-bold font-mono">
              <Wifi className="w-3.5 h-3.5 text-[#1B4332]" />
              <span>ONLINE — LAN FIELD MESH CONNECTED</span>
            </div>
            <span className="text-[10px] text-emerald-700 hidden md:inline font-mono">
              (Live Telemetry &bull; Zero WAN Required)
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-500 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-600"></span>
            </span>
            <div className="flex items-center gap-1.5 font-bold font-mono text-amber-900">
              <WifiOff className="w-3.5 h-3.5 text-amber-700" />
              <span>OFFLINE FIELD MODE — LOCAL CACHE &amp; INDEXEDDB ACTIVE</span>
            </div>
            <span className="text-[10px] text-amber-800 hidden lg:inline">
              All entries secured in device IndexedDB; zero data loss.
            </span>
          </div>
        )}
      </div>

      {/* Right: Outbox Queue Counter, Manual Sync & PWA Install Controls */}
      <div className="flex items-center gap-2.5 flex-wrap">
        {/* Sync message notice */}
        {syncMessage && (
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/80 border border-slate-300 text-slate-800 flex items-center gap-1 shadow-xs">
            <CheckCircle className="w-3 h-3 text-emerald-600" />
            {syncMessage}
          </span>
        )}

        {/* IndexedDB Store indicator */}
        <div className="flex items-center gap-1 text-[11px] font-mono text-slate-600 bg-white/60 px-2 py-0.5 rounded border border-slate-200">
          <Database className="w-3 h-3 text-[#1B4332]" />
          <span>Local Storage: OK</span>
        </div>

        {/* Pending Outbox Counter */}
        {pendingCount > 0 ? (
          <div className="flex items-center gap-1.5 bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded font-mono font-bold text-[11px] animate-pulse">
            <span>⚡ {pendingCount} offline action{pendingCount > 1 ? 's' : ''} queued</span>
          </div>
        ) : (
          <div className="hidden sm:flex items-center gap-1 text-[11px] font-mono text-slate-600">
            <span>Outbox synced</span>
          </div>
        )}

        {/* Manual Sync Trigger Button */}
        <button
          onClick={handleManualSync}
          disabled={isSyncing}
          title="Force flush IndexedDB outbox queue to local mesh"
          className="px-2.5 py-1 rounded bg-[#1B4332] hover:bg-[#143225] disabled:bg-slate-400 text-white font-medium text-xs flex items-center gap-1.5 shadow-xs transition"
        >
          <RefreshCw className={`w-3 h-3 ${isSyncing ? 'animate-spin' : ''}`} />
          <span>{isSyncing ? 'Syncing...' : 'Sync Now'}</span>
        </button>

        {/* PWA Install Button (if browser prompt available) */}
        {deferredPrompt && !isStandalone && (
          <button
            onClick={handleInstallClick}
            className="px-2.5 py-1 rounded bg-[#00E5FF] hover:bg-[#00B4D8] text-slate-950 font-bold text-xs flex items-center gap-1.5 shadow-xs transition"
            title="Install RescueNet Progressive Web App on Android"
          >
            <Smartphone className="w-3.5 h-3.5" />
            <span>Install App</span>
          </button>
        )}

        {/* Standalone badge if already running in standalone PWA mode */}
        {isStandalone && (
          <span className="hidden md:inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 bg-slate-900 text-cyan-300 rounded border border-cyan-800">
            <Smartphone className="w-3 h-3" />
            <span>STANDALONE PWA</span>
          </span>
        )}
      </div>
    </div>
  );
};
