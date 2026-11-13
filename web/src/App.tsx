import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { Navigation, ViewType } from './components/Navigation';
import { Terrain3DView } from './components/views/Terrain3DView';
import { OverviewView } from './components/views/OverviewView';
import { Map2DView } from './components/views/Map2DView';
import { TopologyView } from './components/views/TopologyView';
import { StationsView } from './components/views/StationsView';
import { CommsMonitorView } from './components/views/CommsMonitorView';
import { EventExplorerView } from './components/views/EventExplorerView';
import { ResourcesView } from './components/views/ResourcesView';
import { AnalyticsView } from './components/views/AnalyticsView';
import { ScenariosView } from './components/views/ScenariosView';
import { ReportsView } from './components/views/ReportsView';
import { HackathonDemoModal } from './components/HackathonDemoModal';
import { QuickActionDock } from './components/QuickActionDock';
import { useSimulationSocket } from './hooks/useSimulationSocket';
import { TerrainData, StationData, LinkData } from './types';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginPage } from './components/LoginPage';
import { NetworkStatusBar } from './components/NetworkStatusBar';
import { offlineStorage } from './services/offlineStorage';

const DEFAULT_STATIONS: Record<string, StationData> = {
  alpha: {
    id: 'alpha',
    name: 'Alpha — Harbor Operations Command',
    role: 'Harbor Command & Central Logistics',
    coords: [12, 18],
    elevation_m: 320,
    lat: 30.142,
    lon: 78.412,
    antenna_mast_m: 18,
    status: 'ONLINE',
    is_relay_only: false,
    has_p2p: true,
    battery_pct: 94,
    battery_wh: 480,
    events_count: 142,
    version_vector: { alpha: 142, beta: 118, charlie: 95, delta: 84, echo: 62 },
    tx_packets: 312,
    rx_packets: 298,
    dropped_packets: 4,
    bytes_sent: 45280,
    bytes_received: 42100,
    queue_depth: 0,
    last_seen: Date.now(),
  },
  beta: {
    id: 'beta',
    name: 'Beta — Triage & Field Hospital',
    role: 'Emergency Medical & Evacuation Triage',
    coords: [24, 30],
    elevation_m: 780,
    lat: 30.224,
    lon: 78.508,
    antenna_mast_m: 15,
    status: 'ONLINE',
    is_relay_only: false,
    has_p2p: false,
    battery_pct: 88,
    battery_wh: 420,
    events_count: 118,
    version_vector: { alpha: 142, beta: 118, charlie: 95, delta: 84, echo: 62 },
    tx_packets: 260,
    rx_packets: 274,
    dropped_packets: 2,
    bytes_sent: 38400,
    bytes_received: 41200,
    queue_depth: 0,
    last_seen: Date.now(),
  },
  charlie: {
    id: 'charlie',
    name: 'Charlie — High Mountain Relay',
    role: 'Mountain High Pass Backbone Relay',
    coords: [34, 16],
    elevation_m: 2150,
    lat: 30.298,
    lon: 78.384,
    antenna_mast_m: 24,
    status: 'ONLINE',
    is_relay_only: true,
    has_p2p: false,
    battery_pct: 76,
    battery_wh: 380,
    events_count: 95,
    version_vector: { alpha: 142, beta: 118, charlie: 95, delta: 84, echo: 62 },
    tx_packets: 480,
    rx_packets: 495,
    dropped_packets: 6,
    bytes_sent: 68400,
    bytes_received: 71200,
    queue_depth: 0,
    last_seen: Date.now(),
  },
  delta: {
    id: 'delta',
    name: 'Delta — Valley Supply Depot',
    role: 'Valley Forward Staging & Supply Depot',
    coords: [42, 28],
    elevation_m: 640,
    lat: 30.342,
    lon: 78.532,
    antenna_mast_m: 12,
    status: 'ONLINE',
    is_relay_only: false,
    has_p2p: false,
    battery_pct: 82,
    battery_wh: 390,
    events_count: 84,
    version_vector: { alpha: 142, beta: 118, charlie: 95, delta: 84, echo: 62 },
    tx_packets: 198,
    rx_packets: 210,
    dropped_packets: 3,
    bytes_sent: 27800,
    bytes_received: 31000,
    queue_depth: 0,
    last_seen: Date.now(),
  },
  echo: {
    id: 'echo',
    name: 'Echo — River Crossing Ferry',
    role: 'River Evacuation Route & Water Amb',
    coords: [18, 38],
    elevation_m: 410,
    lat: 30.185,
    lon: 78.584,
    antenna_mast_m: 12,
    status: 'ONLINE',
    is_relay_only: false,
    has_p2p: false,
    battery_pct: 71,
    battery_wh: 340,
    events_count: 62,
    version_vector: { alpha: 142, beta: 118, charlie: 95, delta: 84, echo: 62 },
    tx_packets: 145,
    rx_packets: 160,
    dropped_packets: 1,
    bytes_sent: 19800,
    bytes_received: 22400,
    queue_depth: 0,
    last_seen: Date.now(),
  },
};

const DEFAULT_LINKS: LinkData[] = [
  {
    node_a: 'alpha',
    node_b: 'beta',
    is_connected: true,
    is_manually_cut: false,
    status: 'ACTIVE',
    distance_km: 17.0,
    has_los: true,
    margin_db: 14.2,
    rx_power_dbm: -98.4,
    snr_db: 6.8,
    per: 0.012,
    throughput_bps: 5468,
    latency_ms: 184,
    frequency_mhz: 866.0,
    free_space_loss_db: 115.8,
    terrain_diffraction_loss_db: 0.0,
  },
  {
    node_a: 'beta',
    node_b: 'charlie',
    is_connected: true,
    is_manually_cut: false,
    status: 'ACTIVE',
    distance_km: 17.2,
    has_los: true,
    margin_db: 18.6,
    rx_power_dbm: -94.1,
    snr_db: 8.5,
    per: 0.008,
    throughput_bps: 5468,
    latency_ms: 192,
    frequency_mhz: 866.0,
    free_space_loss_db: 115.9,
    terrain_diffraction_loss_db: 0.0,
  },
  {
    node_a: 'charlie',
    node_b: 'delta',
    is_connected: true,
    is_manually_cut: false,
    status: 'ACTIVE',
    distance_km: 14.4,
    has_los: true,
    margin_db: 11.8,
    rx_power_dbm: -101.2,
    snr_db: 4.2,
    per: 0.024,
    throughput_bps: 5468,
    latency_ms: 210,
    frequency_mhz: 866.0,
    free_space_loss_db: 114.3,
    terrain_diffraction_loss_db: 0.0,
  },
  {
    node_a: 'alpha',
    node_b: 'echo',
    is_connected: true,
    is_manually_cut: false,
    status: 'ACTIVE',
    distance_km: 20.9,
    has_los: true,
    margin_db: 9.4,
    rx_power_dbm: -103.5,
    snr_db: 3.1,
    per: 0.038,
    throughput_bps: 5468,
    latency_ms: 225,
    frequency_mhz: 866.0,
    free_space_loss_db: 117.6,
    terrain_diffraction_loss_db: 0.0,
  },
  {
    node_a: 'delta',
    node_b: 'echo',
    is_connected: true,
    is_manually_cut: false,
    status: 'ACTIVE',
    distance_km: 26.0,
    has_los: false,
    margin_db: 2.1,
    rx_power_dbm: -110.8,
    snr_db: -1.2,
    per: 0.095,
    throughput_bps: 2734,
    latency_ms: 340,
    frequency_mhz: 866.0,
    free_space_loss_db: 119.5,
    terrain_diffraction_loss_db: 8.4,
  },
];

function DashboardContent() {
  const { user, token, isLoading, apiFetch } = useAuth();

  const getInitialView = (): ViewType => {
    if (typeof window !== 'undefined') {
      const hash = window.location.hash.replace('#', '') as ViewType;
      const validViews: ViewType[] = [
        'overview', 'terrain3d', 'map2d', 'topology', 'stations',
        'comms', 'events', 'resources', 'analytics', 'scenarios', 'reports'
      ];
      if (validViews.includes(hash)) return hash;
    }
    return 'overview';
  };

  const [currentView, setCurrentView] = useState<ViewType>(getInitialView);
  const [terrain, setTerrain] = useState<TerrainData | null>(null);
  const [stations, setStations] = useState<Record<string, StationData>>(DEFAULT_STATIONS);
  const [links, setLinks] = useState<LinkData[]>(DEFAULT_LINKS);
  const [demoOpen, setDemoOpen] = useState(false);
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);

  // Sync hash when view changes
  const handleViewChange = (v: ViewType) => {
    setCurrentView(v);
    if (typeof window !== 'undefined') {
      window.location.hash = v;
    }
  };

  // Listen to hashchange
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '') as ViewType;
      const validViews: ViewType[] = [
        'overview', 'terrain3d', 'map2d', 'topology', 'stations',
        'comms', 'events', 'resources', 'analytics', 'scenarios', 'reports'
      ];
      if (validViews.includes(hash)) {
        setCurrentView(hash);
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const { connected, metrics, stations: wsStations } = useSimulationSocket(token);

  // Merge WebSocket stations with local state
  useEffect(() => {
    if (wsStations && Object.keys(wsStations).length > 0) {
      setStations(wsStations);
    }
  }, [wsStations]);

  // Initial fetch for terrain, stations, and links with local storage fallback
  const refreshAll = () => {
    apiFetch('/api/terrain')
      .then((r) => r.json())
      .then((d) => {
        if (d && !d.offline && !d.error) {
          setTerrain(d);
          try {
            localStorage.setItem('rescuenet_cache_terrain', JSON.stringify(d));
          } catch {}
        }
      })
      .catch(() => {
        try {
          const cached = localStorage.getItem('rescuenet_cache_terrain');
          if (cached) setTerrain(JSON.parse(cached));
        } catch {}
      });

    apiFetch('/api/stations')
      .then((r) => r.json())
      .then((data: StationData[]) => {
        if (Array.isArray(data)) {
          const map: Record<string, StationData> = {};
          data.forEach((s) => {
            map[s.id] = s;
          });
          setStations(map);
          try {
            localStorage.setItem('rescuenet_cache_stations', JSON.stringify(map));
          } catch {}
        }
      })
      .catch(() => {
        try {
          const cached = localStorage.getItem('rescuenet_cache_stations');
          if (cached) setStations(JSON.parse(cached));
        } catch {}
      });

    apiFetch('/api/links')
      .then((r) => r.json())
      .then((data: LinkData[]) => {
        if (Array.isArray(data)) {
          setLinks(data);
          try {
            localStorage.setItem('rescuenet_cache_links', JSON.stringify(data));
          } catch {}
        }
      })
      .catch(() => {
        try {
          const cached = localStorage.getItem('rescuenet_cache_links');
          if (cached) setLinks(JSON.parse(cached));
        } catch {}
      });
  };

  useEffect(() => {
    if (!user) return;
    refreshAll();
    const interval = setInterval(() => {
      apiFetch('/api/links')
        .then((r) => r.json())
        .then((data: LinkData[]) => setLinks(data))
        .catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [user]);

  // Keyboard Shortcuts (1-9 for views, Escape for modal close)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }
      if (e.key === 'Escape') {
        setDemoOpen(false);
      } else if (e.key === '1') handleViewChange('overview');
      else if (e.key === '2') handleViewChange('terrain3d');
      else if (e.key === '3') handleViewChange('map2d');
      else if (e.key === '4') handleViewChange('topology');
      else if (e.key === '5') handleViewChange('stations');
      else if (e.key === '6') handleViewChange('comms');
      else if (e.key === '7') handleViewChange('events');
      else if (e.key === '8') handleViewChange('resources');
      else if (e.key === '9') handleViewChange('analytics');
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleToggleLink = async (n1: string, n2: string) => {
    await apiFetch('/api/links/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_a: n1, node_b: n2 }),
    });
    refreshAll();
  };

  const handleHealAll = async () => {
    await apiFetch('/api/links/heal-all', { method: 'POST' });
    refreshAll();
  };

  const handleTriggerSOS = async (msg: string) => {
    try {
      const res = await apiFetch('/api/actions/sos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: 'alpha', message: msg, urgency: 'CRITICAL' }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch {
      // Save locally in IndexedDB & queue in outbox for mesh synchronization
      await offlineStorage.addLocalSOSAlert('alpha', msg);
    }
    refreshAll();
  };

  const handleSelectStation = (id: string) => {
    setSelectedStationId(id);
    handleViewChange('stations');
  };

  // Loading state while verifying credentials or session
  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#060A10] flex flex-col items-center justify-center text-slate-300 font-mono text-sm space-y-4">
        <div className="w-10 h-10 border-2 border-[#00E5FF] border-t-transparent rounded-full animate-spin" />
        <p className="tracking-widest text-xs uppercase text-slate-400">VERIFYING OPERATOR CLEARANCE...</p>
      </div>
    );
  }

  // Unauthenticated: display defense-grade Login Page
  if (!user) {
    return <LoginPage />;
  }

  return (
    <div className="min-h-screen bg-[#F4F6F8] text-[#0F172A] flex flex-col font-sans selection:bg-[#1B4332] selection:text-white">
      {/* Top Header Bar */}
      <Header
        metrics={metrics}
        onOpenDemo={() => setDemoOpen(true)}
        onTriggerSOS={handleTriggerSOS}
      />

      {/* Visible Online / Offline Status Bar & IndexedDB Sync Queue */}
      <NetworkStatusBar wsConnected={connected} />

      {/* Main Work Area: Compact Left Sidebar + Central Operational View */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Navigation Sidebar */}
        <Navigation
          currentView={currentView}
          onViewChange={handleViewChange}
          conflictsCount={metrics?.application.conflicts_detected ?? 0}
          unreachableCount={metrics?.network.is_partitioned ? metrics.network.connected_islands - 1 : 0}
        />

        {/* Central View Content Container */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 pb-20">
          {currentView === 'overview' && (
            <OverviewView
              metrics={metrics}
              stations={stations}
              links={links}
              terrain={terrain}
              onNavigate={handleViewChange}
              onSelectStation={handleSelectStation}
            />
          )}

          {currentView === 'terrain3d' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                    3D Digital Elevation Model &bull; 50 km &times; 50 km Mountain Twin
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Realistic topographic elevation colormap with station masts and parabolic LoRa communication lines.
                  </p>
                </div>
              </div>
              <Terrain3DView
                terrain={terrain}
                stations={stations}
                links={links}
                onSelectStation={handleSelectStation}
                selectedStationId={selectedStationId}
              />
            </div>
          )}

          {currentView === 'map2d' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                    2D Topographic Tactical Map (50 km &times; 50 km)
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Cartographic view showing elevation relief, river gorge, Trishul ridge, and active radio links.
                  </p>
                </div>
              </div>
              <Map2DView
                terrain={terrain}
                stations={stations}
                links={links}
                onSelectStation={handleSelectStation}
              />
            </div>
          )}

          {currentView === 'topology' && (
            <TopologyView
              stations={stations}
              links={links}
              onToggleLink={handleToggleLink}
              onHealAll={handleHealAll}
            />
          )}

          {currentView === 'stations' && (
            <StationsView
              stations={stations}
              onRefresh={refreshAll}
            />
          )}

          {currentView === 'comms' && (
            <CommsMonitorView
              stations={stations}
              onTriggerSync={refreshAll}
            />
          )}

          {currentView === 'events' && (
            <EventExplorerView
              stations={stations}
              onRefresh={refreshAll}
            />
          )}

          {currentView === 'resources' && (
            <ResourcesView
              stations={stations}
              onRefresh={refreshAll}
            />
          )}

          {currentView === 'analytics' && (
            <AnalyticsView
              metrics={metrics}
            />
          )}

          {currentView === 'scenarios' && (
            <ScenariosView
              onRefresh={refreshAll}
            />
          )}

          {currentView === 'reports' && (
            <ReportsView
              metrics={metrics}
            />
          )}
        </main>
      </div>

      {/* Industrial Emergency Operations Command Bar */}
      <QuickActionDock
        onOpenDemo={() => setDemoOpen(true)}
        onRefreshAll={refreshAll}
        onTriggerSOS={handleTriggerSOS}
      />

      {/* 5-Minute Emergency Operations Demonstration Stepper */}
      <HackathonDemoModal
        isOpen={demoOpen}
        onClose={() => setDemoOpen(false)}
        onRefresh={refreshAll}
      />
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <DashboardContent />
    </AuthProvider>
  );
}

export default App;
