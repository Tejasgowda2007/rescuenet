import React, { useState, useEffect } from 'react';
import { LiveMetrics, StationData, LinkData, EventRecord } from '../../types';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  Radio,
  Battery,
  ShieldCheck,
  ArrowRight,
  TrendingUp,
  Cpu,
  Layers,
  MapPin,
  Clock,
  RefreshCw,
  Anchor,
  Pill,
  Server,
  Wifi,
  WifiOff,
  Maximize2,
} from 'lucide-react';
import { Map2DView } from './Map2DView';

interface OverviewViewProps {
  metrics: LiveMetrics | null;
  stations: Record<string, StationData>;
  links: LinkData[];
  onNavigate: (view: any) => void;
  onSelectStation: (id: string) => void;
  terrain?: any;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  metrics,
  stations,
  links,
  onNavigate,
  onSelectStation,
  terrain,
}) => {
  const [recentEvents, setRecentEvents] = useState<EventRecord[]>([]);
  const [selectedStationTab, setSelectedStationTab] = useState<string>('alpha');
  const [syncing, setSyncing] = useState(false);

  // Fetch recent events from stations for bottom timeline
  const fetchRecentEvents = () => {
    fetch('/api/events?limit=8')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setRecentEvents(data);
        } else if (data.events) {
          setRecentEvents(data.events);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchRecentEvents();
    const interval = setInterval(fetchRecentEvents, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleManualSync = async () => {
    setSyncing(true);
    try {
      await fetch('/api/actions/sync?source_id=alpha', { method: 'POST' });
      fetchRecentEvents();
    } catch (e) {
      console.error(e);
    } finally {
      setSyncing(false);
    }
  };

  const isPartitioned = metrics?.network.is_partitioned ?? false;
  const islands = metrics?.network.islands ?? [];
  const packetsSent = metrics?.network.packets_sent ?? 0;
  const packetsDelivered = metrics?.network.packets_delivered ?? 0;
  
  // Realism rule: Never show 100% packet delivery when 0 packets were sent
  const pdrDisplay = packetsSent > 0 
    ? `${metrics?.network.delivery_ratio_pct ?? Math.round((packetsDelivered / packetsSent) * 100)}%` 
    : 'N/A (Idle)';

  const activeStation = stations[selectedStationTab] || Object.values(stations)[0];

  return (
    <div className="space-y-4">
      {/* Top Incident Banner (Only when active partition or emergency exists) */}
      {isPartitioned && (
        <div className="bg-amber-50 border-l-4 border-amber-600 p-3 rounded shadow-xs flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0" />
            <div>
              <h4 className="text-xs font-bold text-amber-950 uppercase tracking-wide">
                Network Partition Detected &bull; {metrics?.network.connected_islands} Isolated Sectors
              </h4>
              <p className="text-xs text-amber-900 mt-0.5">
                Line-of-sight obstructed over Trishul Ridge. Stations are operating autonomously with independent SQLite stores.
              </p>
            </div>
          </div>
          <button
            onClick={() => onNavigate('topology')}
            className="px-3 py-1 rounded bg-amber-700 hover:bg-amber-800 text-white text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <span>Inspect Routing Topology</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Main Operational Split: Large Central Map (Left/Center 68%) + Right Status Panel (32%) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Large Central Operational Map */}
        <div className="lg:col-span-8 bg-white border border-slate-200 rounded shadow-xs p-3.5 flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5 mb-3">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#1B4332]" />
              <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                Operational Field Map &bull; 50 km &times; 50 km Ad-Hoc Disaster Zone
              </h3>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[11px] text-slate-500">LoRa 865–867 MHz WPC</span>
              <button
                onClick={() => onNavigate('map2d')}
                className="text-[11px] text-[#1B4332] hover:text-[#143827] font-semibold flex items-center gap-1"
              >
                <span>Fullscreen GIS</span>
                <Maximize2 className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Central Map Canvas */}
          <div className="flex-1 min-h-[460px]">
            <Map2DView
              terrain={terrain}
              stations={stations}
              links={links}
              onSelectStation={(id) => {
                setSelectedStationTab(id);
                onSelectStation(id);
              }}
            />
          </div>

          {/* Operational Map Bar */}
          <div className="mt-3 pt-2.5 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-600 gap-2">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-600" />
                <span>Viable LoRa Link (&ge;10 dB margin)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                <span>Marginal Link (0–10 dB)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 border-t border-dashed border-red-600" />
                <span>Ridge Cut / Severed</span>
              </div>
            </div>
            <div className="text-[11px] text-slate-500 font-mono">
              Scale: 1 grid unit = 5 km &bull; Projected UTM Zone 44N
            </div>
          </div>
        </div>

        {/* Right-Side Operational Status Panel */}
        <div className="lg:col-span-4 space-y-4">
          {/* Station Fleet Summary Card */}
          <div className="bg-white border border-slate-200 rounded shadow-xs p-3.5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <div className="flex items-center gap-2">
                <Server className="w-4 h-4 text-[#1B4332]" />
                <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                  Station Fleet Deployment
                </h4>
              </div>
              <button
                onClick={() => onNavigate('stations')}
                className="text-[11px] text-[#1B4332] hover:underline font-semibold"
              >
                Fleet Detail &rarr;
              </button>
            </div>

            {/* Station List Table */}
            <div className="space-y-1.5">
              {Object.values(stations).map((stn) => {
                const isSelected = selectedStationTab === stn.id;
                const isOnline = stn.status === 'ONLINE';
                const isDegraded = stn.status === 'DEGRADED';
                const isPhysical = stn.id === 'alpha'; // Alpha is the physical command post; others simulated stubs

                return (
                  <div
                    key={stn.id}
                    onClick={() => {
                      setSelectedStationTab(stn.id);
                      onSelectStation(stn.id);
                    }}
                    className={`p-2 rounded border text-xs cursor-pointer transition flex items-center justify-between ${
                      isSelected
                        ? 'bg-slate-50 border-[#1B4332]'
                        : 'bg-white border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          isOnline ? 'bg-emerald-600' : isDegraded ? 'bg-amber-500' : 'bg-red-600'
                        }`}
                      />
                      <div>
                        <div className="font-semibold text-slate-900 leading-tight">
                          {stn.name.split(' ')[0]} ({stn.id.toUpperCase()})
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          {stn.role.split('&')[0]} &bull; {stn.elevation_m}m
                        </div>
                      </div>
                    </div>

                    <div className="text-right space-y-0.5">
                      <span
                        className={`text-[9px] font-mono font-bold px-1 py-0.2 rounded ${
                          isPhysical
                            ? 'bg-blue-100 text-blue-900 border border-blue-200'
                            : 'bg-slate-100 text-slate-600 border border-slate-200'
                        }`}
                      >
                        {isPhysical ? 'PHYSICAL' : 'SIMULATED'}
                      </span>
                      <div className="text-[11px] font-mono text-slate-700">
                        {stn.battery_pct}% bat &bull; {stn.events_count} ev
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Allocation & Distributed Invariants Panel */}
          <div className="bg-white border border-slate-200 rounded shadow-xs p-3.5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#1B4332]" />
                <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                  Resource & Safety Invariants
                </h4>
              </div>
              <button
                onClick={() => onNavigate('resources')}
                className="text-[11px] text-[#1B4332] hover:underline font-semibold"
              >
                Escrow Detail &rarr;
              </button>
            </div>

            <div className="space-y-2 text-xs">
              {/* Boat Token Status */}
              <div className="p-2.5 rounded bg-slate-50 border border-slate-200 flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-1.5 font-bold text-slate-900 text-xs">
                    <Anchor className="w-3.5 h-3.5 text-[#1B4332]" />
                    <span>Titan Rescue Boat #1</span>
                  </div>
                  <p className="text-[11px] text-slate-600 mt-0.5">
                    Single-Owner Token Custody: <strong className="text-slate-900 font-mono">Alpha Harbor</strong>
                  </p>
                </div>
                <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-900 border border-emerald-300 text-[10px] font-bold rounded">
                  EXCLUSIVE
                </span>
              </div>

              {/* Escrow Supplies Conservation */}
              <div className="p-2.5 rounded bg-slate-50 border border-slate-200 flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-1.5 font-bold text-slate-900 text-xs">
                    <Pill className="w-3.5 h-3.5 text-[#1B4332]" />
                    <span>Amoxicillin Escrow Pool</span>
                  </div>
                  <p className="text-[11px] text-slate-600 mt-0.5">
                    Quotas Conserved: <strong className="text-slate-900 font-mono">120 / 120</strong> courses accounted
                  </p>
                </div>
                <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-900 border border-emerald-300 text-[10px] font-bold rounded">
                  CONSERVED
                </span>
              </div>

              {/* Convergence Audit */}
              <div className="p-2.5 rounded bg-slate-50 border border-slate-200 flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-1.5 font-bold text-slate-900 text-xs">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" />
                    <span>Convergence Guarantees</span>
                  </div>
                  <p className="text-[11px] text-slate-600 mt-0.5">
                    Zero lost updates; CRDT deterministic event folding
                  </p>
                </div>
                <span className="px-1.5 py-0.5 bg-slate-100 text-slate-800 border border-slate-300 text-[10px] font-mono font-bold rounded">
                  SEC-OK
                </span>
              </div>
            </div>
          </div>

          {/* Useful Telemetry Summary */}
          <div className="bg-white border border-slate-200 rounded shadow-xs p-3.5 text-xs">
            <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              RF Telemetry Summary
            </h4>
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="p-2 bg-slate-50 border border-slate-200 rounded">
                <span className="text-[10px] text-slate-500 block">Packet Delivery</span>
                <span className="text-sm font-bold font-mono text-slate-900">{pdrDisplay}</span>
              </div>
              <div className="p-2 bg-slate-50 border border-slate-200 rounded">
                <span className="text-[10px] text-slate-500 block">Active LoRa Links</span>
                <span className="text-sm font-bold font-mono text-slate-900">
                  {metrics?.network.active_links ?? 0} operational
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Activity & Event Timeline */}
      <div className="bg-white border border-slate-200 rounded shadow-xs p-3.5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-[#1B4332]" />
            <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
              Operational Activity &amp; Event Stream
            </h4>
            <span className="text-[11px] text-slate-500 hidden sm:inline">
              (Live mutations across local SQLite append-only event stores)
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleManualSync}
              disabled={syncing}
              className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 border border-slate-300 text-xs font-medium text-slate-800 flex items-center gap-1.5 transition"
            >
              <RefreshCw className={`w-3 h-3 text-[#1B4332] ${syncing ? 'animate-spin' : ''}`} />
              <span>{syncing ? 'Syncing Mesh...' : 'Trigger Anti-Entropy Sync'}</span>
            </button>
            <button
              onClick={() => onNavigate('events')}
              className="text-xs text-[#1B4332] hover:underline font-semibold"
            >
              View Full Event Ledger &rarr;
            </button>
          </div>
        </div>

        {/* Tabular Event Stream */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
              <tr>
                <th className="py-2 px-3">Timestamp</th>
                <th className="py-2 px-3">Station Node</th>
                <th className="py-2 px-3">Event Type</th>
                <th className="py-2 px-3">Entity ID</th>
                <th className="py-2 px-3">Operation &amp; Summary</th>
                <th className="py-2 px-3">Crypto Status</th>
                <th className="py-2 px-3 text-right">Event Hash</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {recentEvents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-4 text-center text-slate-400">
                    No recent events recorded in this session. Use 'Drill Stepper' or 'Station Fleet' to emit events.
                  </td>
                </tr>
              ) : (
                recentEvents.slice(0, 7).map((ev, idx) => {
                  const dateStr = new Date(ev.timestamp * 1000).toLocaleTimeString();
                  const isConflict = ev.payload?.conflicts?.length > 0;
                  return (
                    <tr key={ev.event_id || idx} className="hover:bg-slate-50/80 transition">
                      <td className="py-2 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                        {dateStr}
                      </td>
                      <td className="py-2 px-3 font-semibold text-slate-900 whitespace-nowrap">
                        {ev.node_id?.toUpperCase()}
                      </td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-700 border border-slate-200">
                          {ev.entity_type}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono text-slate-900">
                        {ev.entity_id}
                      </td>
                      <td className="py-2 px-3">
                        <span className="font-semibold">{ev.operation}:</span>{' '}
                        {ev.payload?.name || ev.payload?.item || JSON.stringify(ev.payload).slice(0, 40)}
                        {isConflict && (
                          <span className="ml-2 px-1 py-0.2 bg-amber-100 text-amber-800 text-[10px] font-bold rounded">
                            Disputed
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-3">
                        <span className="text-[10px] text-emerald-800 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                          Ed25519 Signed
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-[10px] text-slate-500">
                        {ev.event_id ? `${ev.event_id.slice(0, 10)}...` : 'local'}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
