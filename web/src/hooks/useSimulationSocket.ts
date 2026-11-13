import { useEffect, useState, useRef } from 'react';
import { LiveMetrics, StationData } from '../types';

export function useSimulationSocket(authToken?: string | null) {
  const [connected, setConnected] = useState(false);
  const [metrics, setMetrics] = useState<LiveMetrics | null>(null);
  const [stations, setStations] = useState<Record<string, StationData>>({});
  const [recentPackets, setRecentPackets] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let unmounted = false;
    const token = authToken || localStorage.getItem('rescuenet_token');
    const apiBase = (import.meta as any).env?.VITE_API_URL || '';

    function connect() {
      let wsHost = window.location.host;
      let wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

      if (apiBase) {
        try {
          const u = new URL(apiBase);
          wsHost = u.host;
          wsProtocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
        } catch (e) {}
      }

      const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
      const url = `${wsProtocol}//${wsHost}/ws${tokenParam}`;

      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!unmounted) setConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'TELEMETRY_TICK') {
              if (data.metrics) setMetrics(data.metrics);
              if (data.stations) setStations(data.stations);
              if (data.recent_packets) setRecentPackets(data.recent_packets);
            }
          } catch (e) {
            console.error('WS parse error', e);
          }
        };

        ws.onclose = (ev) => {
          if (!unmounted) {
            setConnected(false);
            // If closed due to unauthorized (1008), do not spam reconnect
            if (ev.code !== 1008) {
              setTimeout(connect, 2000);
            }
          }
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (err) {
        console.error('WebSocket connection error', err);
      }
    }

    connect();

    // Fallback initial REST fetch with bearer authorization
    const restBase = apiBase ? apiBase.replace(/\/+$/, '') : '';
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    fetch(`${restBase}/api/metrics`, { headers, credentials: 'include' })
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        if (!unmounted && data) setMetrics(data);
      })
      .catch(() => {});

    return () => {
      unmounted = true;
      if (wsRef.current) wsRef.current.close();
    };
  }, [authToken]);

  return { connected, metrics, stations, recentPackets };
}
