/**
 * Google Nearby Connections Android JavaScript Bridge for RescueNet.
 * 
 * When running inside the native Android wrapper (MainActivity + WebView),
 * this module communicates with the native Android Google Nearby Connections
 * mesh service via window.AndroidNearby.
 * 
 * When running in standard mobile browsers (Chrome / Edge PWA), it safely
 * detects that native nearby is unavailable and defers to LAN Wi-Fi / Hotspot transport.
 */

declare global {
  interface Window {
    AndroidNearby?: {
      isAvailable: () => boolean;
      startMesh: (nodeId: string) => boolean;
      stopMesh: () => void;
      getConnectedPeers: () => string; // Returns JSON string array of peer IDs
      broadcastPayload: (base64Payload: string) => boolean;
      sendToPeer: (peerId: string, base64Payload: string) => boolean;
    };
  }
}

export interface NearbyPeer {
  endpointId: string;
  name: string;
  connectedAt: number;
}

let activePeers: Map<string, NearbyPeer> = new Map();
const peerListeners: Set<(peers: NearbyPeer[]) => void> = new Set();
let isInitialized = false;

export function isNearbyMeshAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  return Boolean(window.AndroidNearby && window.AndroidNearby.isAvailable());
}

export function startNearbyMesh(nodeId: string): boolean {
  if (!isNearbyMeshAvailable()) {
    console.log('[NearbyBridge] Native Nearby Connections not available in browser; using standard LAN transport.');
    return false;
  }
  try {
    return window.AndroidNearby!.startMesh(nodeId);
  } catch (err) {
    console.error('[NearbyBridge] Error starting nearby mesh:', err);
    return false;
  }
}

export function stopNearbyMesh(): void {
  if (isNearbyMeshAvailable()) {
    try {
      window.AndroidNearby!.stopMesh();
      activePeers.clear();
      notifyPeerListeners();
    } catch (err) {
      console.error('[NearbyBridge] Error stopping nearby mesh:', err);
    }
  }
}

export function getConnectedNearbyPeers(): NearbyPeer[] {
  return Array.from(activePeers.values());
}

export function subscribeNearbyPeers(callback: (peers: NearbyPeer[]) => void): () => void {
  peerListeners.add(callback);
  callback(Array.from(activePeers.values()));
  return () => peerListeners.delete(callback);
}

function notifyPeerListeners() {
  const list = Array.from(activePeers.values());
  peerListeners.forEach((cb) => {
    try {
      cb(list);
    } catch {}
  });
}

export function broadcastNearbyPayload(payloadBase64: string): boolean {
  if (!isNearbyMeshAvailable()) return false;
  try {
    return window.AndroidNearby!.broadcastPayload(payloadBase64);
  } catch (err) {
    console.error('[NearbyBridge] Error broadcasting nearby payload:', err);
    return false;
  }
}

export function sendNearbyToPeer(peerId: string, payloadBase64: string): boolean {
  if (!isNearbyMeshAvailable()) return false;
  try {
    return window.AndroidNearby!.sendToPeer(peerId, payloadBase64);
  } catch (err) {
    console.error('[NearbyBridge] Error sending to peer:', err);
    return false;
  }
}

export function decodeNearbyPayload(base64Str: string): any {
  try {
    const raw = decodeURIComponent(escape(atob(base64Str)));
    return JSON.parse(raw);
  } catch {
    try {
      const raw = atob(base64Str);
      return JSON.parse(raw);
    } catch (e) {
      console.warn('[NearbyBridge] Failed to decode payload:', e);
      return null;
    }
  }
}

export function encodeNearbyPayload(data: any): string {
  const json = JSON.stringify(data);
  return btoa(unescape(encodeURIComponent(json)));
}

export function initNearbyBridge(
  localNodeId: string,
  handlers?: {
    onIncidentReceived?: (incident: any) => void;
    onMessageReceived?: (message: any) => void;
    onAlertReceived?: (alert: any) => void;
  }
): () => void {
  if (typeof window === 'undefined') return () => {};
  if (isInitialized) return () => {};
  isInitialized = true;

  if (isNearbyMeshAvailable()) {
    startNearbyMesh(localNodeId);
  }

  // Handle incoming payloads from peer devices
  const payloadHandler = (event: Event) => {
    const custom = event as CustomEvent<{ endpointId: string; payloadBase64: string }>;
    if (!custom.detail || !custom.detail.payloadBase64) return;

    const data = decodeNearbyPayload(custom.detail.payloadBase64);
    if (!data) return;

    console.log(`[NearbyBridge] Incoming payload from peer ${custom.detail.endpointId}:`, data.type);

    if (data.type === 'INCIDENT' && handlers?.onIncidentReceived) {
      handlers.onIncidentReceived(data.data);
    } else if (data.type === 'MESSAGE' && handlers?.onMessageReceived) {
      handlers.onMessageReceived(data.data);
    } else if (data.type === 'SOS' && handlers?.onAlertReceived) {
      handlers.onAlertReceived(data.data);
    }

    // Also dispatch general window event for any view to react
    window.dispatchEvent(new CustomEvent('rescuenet-peer-data-received', { detail: data }));
  };

  const peerConnectedHandler = (event: Event) => {
    const custom = event as CustomEvent<{ endpointId: string; name?: string }>;
    if (custom.detail && custom.detail.endpointId) {
      activePeers.set(custom.detail.endpointId, {
        endpointId: custom.detail.endpointId,
        name: custom.detail.name || custom.detail.endpointId,
        connectedAt: Date.now(),
      });
      notifyPeerListeners();
      console.log('[NearbyBridge] Peer connected:', custom.detail.endpointId, custom.detail.name);
    }
  };

  const peerDisconnectedHandler = (event: Event) => {
    const custom = event as CustomEvent<{ endpointId: string }>;
    if (custom.detail && custom.detail.endpointId) {
      activePeers.delete(custom.detail.endpointId);
      notifyPeerListeners();
      console.log('[NearbyBridge] Peer disconnected:', custom.detail.endpointId);
    }
  };

  window.addEventListener('rescuenet-nearby-payload', payloadHandler);
  window.addEventListener('rescuenet-peer-connected', peerConnectedHandler);
  window.addEventListener('rescuenet-peer-disconnected', peerDisconnectedHandler);

  return () => {
    window.removeEventListener('rescuenet-nearby-payload', payloadHandler);
    window.removeEventListener('rescuenet-peer-connected', peerConnectedHandler);
    window.removeEventListener('rescuenet-peer-disconnected', peerDisconnectedHandler);
    isInitialized = false;
  };
}
