import React, { useEffect, useState } from 'react';
import { PacketRecord, StationData } from '../../types';
import {
  Activity,
  RefreshCw,
  AlertOctagon,
  CheckCircle2,
  ArrowRight,
  Zap,
  Radio,
  Filter,
  Eye,
  ShieldCheck,
  Cpu,
  Layers,
  X,
  Binary,
} from 'lucide-react';

interface CommsMonitorViewProps {
  stations: Record<string, StationData>;
  onTriggerSync?: () => void;
}

export const CommsMonitorView: React.FC<CommsMonitorViewProps> = ({ stations, onTriggerSync }) => {
  const [packets, setPackets] = useState<PacketRecord[]>([]);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>('all');
  const [selectedPacket, setSelectedPacket] = useState<PacketRecord | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchPackets = () => {
    fetch('/api/packets?limit=50')
      .then((r) => r.json())
      .then((data) => setPackets(data))
      .catch(() => {});
  };

  useEffect(() => {
    fetchPackets();
    if (!autoRefresh) return;
    const iv = setInterval(fetchPackets, 1500);
    return () => clearInterval(iv);
  }, [autoRefresh]);

  const handleSyncAll = async () => {
    setSyncStatus('Initiating anti-entropy sync across mesh...');
    try {
      const res = await fetch('/api/actions/sync?source_id=alpha', { method: 'POST' });
      const data = await res.json();
      setSyncStatus(`Sync finished (${data.results?.length ?? 0} links probed)`);
      setTimeout(() => setSyncStatus(null), 4000);
      fetchPackets();
      onTriggerSync?.();
    } catch (e) {
      setSyncStatus('Sync error');
    }
  };

  // Filter packets
  const filteredPackets = packets.filter((pkt) => {
    if (filterType === 'all') return true;
    if (filterType === 'sos') return pkt.msg_type === 'SOS';
    if (filterType === 'sync') return pkt.msg_type === 'SYNC';
    if (filterType === 'telemetry') return pkt.msg_type === 'TELEMETRY';
    if (filterType === 'dropped') return !pkt.delivered;
    return true;
  });

  const totalDelivered = packets.filter((p) => p.delivered).length;
  // Realism: Never show 100% when zero packets were transmitted
  const deliveryRatio = packets.length > 0 ? `${Math.round((totalDelivered / packets.length) * 100)}%` : 'N/A (Idle)';
  const totalWireBytes = packets.reduce((acc, p) => acc + (p.bytes || 0), 0);

  return (
    <div className="space-y-4">
      {/* View Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#1B4332]" />
            <span>Radio Frame Telemetry &amp; Channel Contention Monitor</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Discrete-event SimPy radio frame transmissions, serialization airtimes, queue buffering, and packet loss.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-2.5 py-1 rounded border text-xs font-semibold flex items-center gap-1.5 transition ${
              autoRefresh
                ? 'bg-white border-slate-300 text-slate-700'
                : 'bg-amber-50 border-amber-300 text-amber-800'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${autoRefresh ? 'bg-emerald-600 animate-pulse' : 'bg-slate-400'}`} />
            <span>{autoRefresh ? 'Live Polling 1.5s' : 'Paused'}</span>
          </button>

          <button
            onClick={handleSyncAll}
            className="px-3 py-1 rounded bg-[#1B4332] hover:bg-[#143827] text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Anti-Entropy Delta Sync</span>
          </button>
        </div>
      </div>

      {syncStatus && (
        <div className="p-2.5 bg-emerald-50 border border-emerald-300 text-emerald-900 rounded text-xs font-semibold">
          {syncStatus}
        </div>
      )}

      {/* KPI Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white border border-slate-200 p-3 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 uppercase font-semibold block">Total Radio Frames</span>
          <span className="text-xl font-bold font-mono text-slate-900">{packets.length}</span>
          <span className="text-[10px] text-slate-600 block mt-0.5">{totalDelivered} delivered successfully</span>
        </div>

        <div className="bg-white border border-slate-200 p-3 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 uppercase font-semibold block">Packet Delivery Ratio</span>
          <span className="text-xl font-bold font-mono text-emerald-800">{deliveryRatio}</span>
          <span className="text-[10px] text-slate-600 block mt-0.5">
            {packets.length - totalDelivered} dropped / PER losses
          </span>
        </div>

        <div className="bg-white border border-slate-200 p-3 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 uppercase font-semibold block">Total Framed Wire Traffic</span>
          <span className="text-xl font-bold font-mono text-slate-900">{totalWireBytes} <span className="text-xs font-normal">Bytes</span></span>
          <span className="text-[10px] text-slate-600 block mt-0.5">LoRa PHY frames over air</span>
        </div>

        <div className="bg-white border border-slate-200 p-3 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 uppercase font-semibold block">Channel Frequency</span>
          <span className="text-xl font-bold font-mono text-slate-900">865–867 <span className="text-xs font-normal">MHz</span></span>
          <span className="text-[10px] text-slate-600 block mt-0.5">WPC India ISM Specification</span>
        </div>
      </div>

      {/* Filter Tabs & Packet Table */}
      <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between border-b border-slate-100 pb-2.5 gap-2">
          <div className="flex items-center gap-1.5 text-xs">
            <span className="font-semibold text-slate-500 text-[11px] uppercase tracking-wide mr-1">Filter:</span>
            {[
              { id: 'all', label: 'All Frames' },
              { id: 'sos', label: 'Priority-0 SOS' },
              { id: 'sync', label: 'Priority-1 Sync' },
              { id: 'telemetry', label: 'Priority-2 Telemetry' },
              { id: 'dropped', label: 'Dropped / PER' },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setFilterType(f.id)}
                className={`px-2.5 py-1 rounded text-xs font-medium border transition ${
                  filterType === f.id
                    ? 'bg-[#1B4332] text-white border-[#1B4332]'
                    : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <span className="text-[11px] text-slate-500 font-mono">
            Showing {filteredPackets.length} of {packets.length} frames
          </span>
        </div>

        {/* Tabular Frame Telemetry */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold font-sans">
              <tr>
                <th className="py-2 px-3">Packet ID</th>
                <th className="py-2 px-3">Type</th>
                <th className="py-2 px-3">Priority</th>
                <th className="py-2 px-3">Source &rarr; Target</th>
                <th className="py-2 px-3">Hop Segment</th>
                <th className="py-2 px-3">Wire Size</th>
                <th className="py-2 px-3">Airtime Latency</th>
                <th className="py-2 px-3">Delivery Status</th>
                <th className="py-2 px-3 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 font-sans">
              {filteredPackets.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-4 text-center text-slate-400">
                    No radio packets recorded under current filter.
                  </td>
                </tr>
              ) : (
                filteredPackets.map((pkt) => {
                  const isDelivered = pkt.delivered;
                  const isSOS = pkt.msg_type === 'SOS';

                  return (
                    <tr
                      key={pkt.packet_id}
                      className={`hover:bg-slate-50 transition cursor-pointer ${
                        isSOS ? 'bg-red-50/50' : ''
                      }`}
                      onClick={() => setSelectedPacket(pkt)}
                    >
                      <td className="py-2 px-3 font-mono font-bold text-slate-900">
                        {pkt.packet_id.slice(0, 12)}
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            isSOS
                              ? 'bg-red-100 text-red-900 border border-red-200'
                              : pkt.msg_type === 'SYNC'
                              ? 'bg-emerald-100 text-emerald-900 border border-emerald-200'
                              : 'bg-slate-100 text-slate-700 border border-slate-200'
                          }`}
                        >
                          {pkt.msg_type}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono">P{pkt.priority}</td>
                      <td className="py-2 px-3 font-medium text-slate-900">
                        {pkt.source.toUpperCase()} &rarr; {pkt.destination.toUpperCase()}
                      </td>
                      <td className="py-2 px-3 font-mono text-slate-600 text-[11px]">
                        {pkt.hop_src.toUpperCase()} &bull; {pkt.hop_dst.toUpperCase()}
                      </td>
                      <td className="py-2 px-3 font-mono">{pkt.bytes} B</td>
                      <td className="py-2 px-3 font-mono text-slate-900">
                        {pkt.latency_ms > 0 ? `${pkt.latency_ms} ms` : 'N/A'}
                      </td>
                      <td className="py-2 px-3">
                        {isDelivered ? (
                          <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-800">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" />
                            <span>DELIVERED</span>
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-[11px] font-semibold text-red-700">
                            <AlertOctagon className="w-3.5 h-3.5 text-red-600" />
                            <span>{pkt.reason || 'DROPPED'}</span>
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedPacket(pkt);
                          }}
                          className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] font-bold transition"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Packet Detail Modal */}
      {selectedPacket && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-300 rounded-lg max-w-lg w-full p-5 shadow-lg space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-[#1B4332]" />
                <h3 className="font-bold text-sm text-[#0F172A]">
                  Radio Packet Inspection: {selectedPacket.packet_id.slice(0, 14)}
                </h3>
              </div>
              <button
                onClick={() => setSelectedPacket(null)}
                className="p-1 rounded text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold block">Physical Parameters</span>
                  <span className="font-bold text-slate-900 block mt-0.5">865–867 MHz LoRa</span>
                  <span className="text-[10px] text-slate-600 block">Airtime: {selectedPacket.latency_ms} ms</span>
                </div>
                <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold block">Message Priority</span>
                  <span className="font-bold text-slate-900 block mt-0.5">
                    Priority {selectedPacket.priority} &bull; {selectedPacket.msg_type}
                  </span>
                  <span className="text-[10px] text-slate-600 block">Payload: {selectedPacket.bytes} Bytes</span>
                </div>
              </div>

              <div className="p-2.5 bg-slate-50 rounded border border-slate-200 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-500">Source Station:</span>
                  <span className="font-bold text-slate-900">{selectedPacket.source.toUpperCase()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Destination:</span>
                  <span className="font-bold text-slate-900">{selectedPacket.destination.toUpperCase()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Current Hop:</span>
                  <span className="font-mono text-slate-900">
                    {selectedPacket.hop_src.toUpperCase()} &rarr; {selectedPacket.hop_dst.toUpperCase()}
                  </span>
                </div>
                {selectedPacket.route && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">Dijkstra Route:</span>
                    <span className="font-mono font-bold text-[#1B4332]">
                      {selectedPacket.route.join(' -> ').toUpperCase()}
                    </span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-slate-500">Delivery Status:</span>
                  <span className={`font-bold ${selectedPacket.delivered ? 'text-emerald-800' : 'text-red-700'}`}>
                    {selectedPacket.delivered ? 'ACK DELIVERED' : `DROPPED: ${selectedPacket.reason}`}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedPacket(null)}
                className="px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-700 text-xs font-semibold rounded"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
