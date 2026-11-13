import { useEffect, useState, useRef } from 'react';
import { LiveMetrics, StationData } from '../types';

export function useSimulationSocket() {
  const [connected, setConnected] = useState(false);
  const [metrics, setMetrics] = useState<LiveMetrics | null>(null);
  const [stations, setStations] = useState<Record<string, StationData>>({});
  const [recentPackets, setRecentPackets] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let unmounted = false;

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const url = `${protocol}//${host}/ws`;

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

      ws.onclose = () => {
        if (!unmounted) {
          setConnected(false);
          // Reconnect attempt after 2s
          setTimeout(connect, 2000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    // Fallback initial REST fetch
    fetch('/api/metrics')
      .then(res => res.json())
      .then(data => {
        if (!unmounted) setMetrics(data);
      })
      .catch(() => {});

    return () => {
      unmounted = true;
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return { connected, metrics, stations, recentPackets };
}
