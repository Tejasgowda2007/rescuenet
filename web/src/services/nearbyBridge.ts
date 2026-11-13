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
  nodeId: string;
  connectedAt: number;
}

export function isNearbyMeshAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  return Boolean(window.AndroidNearby && window.AndroidNearby.isAvailable());
}

export function startNearbyMesh(nodeId: string): boolean {
  if (!isNearbyMeshAvailable()) {
    console.log('[NearbyBridge] Native Nearby Connections not available on standard web browser; using LAN mesh.');
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
    } catch (err) {
      console.error('[NearbyBridge] Error stopping nearby mesh:', err);
    }
  }
}

export function getConnectedNearbyPeers(): string[] {
  if (!isNearbyMeshAvailable()) return [];
  try {
    const raw = window.AndroidNearby!.getConnectedPeers();
    return JSON.parse(raw || '[]');
  } catch {
    return [];
  }
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

export function subscribeNearbyPayload(
  callback: (endpointId: string, payloadBase64: string) => void
): () => void {
  if (typeof window === 'undefined') return () => {};

  const handler = (event: Event) => {
    const custom = event as CustomEvent<{ endpointId: string; payloadBase64: string }>;
    if (custom.detail) {
      callback(custom.detail.endpointId, custom.detail.payloadBase64);
    }
  };

  window.addEventListener('rescuenet-nearby-payload', handler);
  return () => window.removeEventListener('rescuenet-nearby-payload', handler);
}
