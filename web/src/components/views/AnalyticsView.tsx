import React, { useEffect, useState } from 'react';
import { LiveMetrics } from '../../types';
import { BarChart3, Activity, Cpu, ShieldAlert, TrendingUp, Radio } from 'lucide-react';

interface AnalyticsViewProps {
  metrics: LiveMetrics | null;
}

export const AnalyticsView: React.FC<AnalyticsViewProps> = ({ metrics }) => {
  const [timeseries, setTimeseries] = useState<any>(null);

  useEffect(() => {
    fetch('/api/metrics/timeseries')
      .then((r) => r.json())
      .then((d) => setTimeseries(d))
      .catch(() => {});
  }, []);

  const net = metrics?.network;
  const packetsSent = net?.packets_sent ?? 0;
  const pdrDisplay = packetsSent > 0 ? `${net?.delivery_ratio_pct ?? 100}%` : 'N/A (Idle)';

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-[#1B4332]" />
          <span>RF Performance Analytics &amp; Discrete-Event Telemetry</span>
        </h3>
        <p className="text-xs text-slate-500 mt-0.5">
          Metrics computed from discrete-event SimPy transmissions, channel contention, and SQLite replication records.
        </p>
      </div>

      {/* KPI Summary Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white border border-slate-200 p-3.5 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 font-semibold uppercase block">Packet Delivery Ratio</span>
          <span className="text-xl font-bold font-mono text-emerald-800">{pdrDisplay}</span>
          <span className="text-[10px] text-slate-500 block mt-0.5">
            {net?.packets_dropped ?? 0} dropped / {packetsSent} sent
          </span>
        </div>

        <div className="bg-white border border-slate-200 p-3.5 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 font-semibold uppercase block">Total Framed Wire Traffic</span>
          <span className="text-xl font-bold font-mono text-slate-900">
            {((net?.total_wire_bytes ?? 0) / 1024).toFixed(1)} <span className="text-xs text-slate-500">KB</span>
          </span>
          <span className="text-[10px] text-slate-500 block mt-0.5">
            {net?.total_wire_bytes ?? 0} framed bytes over air
          </span>
        </div>

        <div className="bg-white border border-slate-200 p-3.5 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 font-semibold uppercase block">Effective Throughput</span>
          <span className="text-xl font-bold font-mono text-slate-900">
            {((net?.effective_throughput_bps ?? 0) / 1000).toFixed(1)} <span className="text-xs text-slate-500">kbps</span>
          </span>
          <span className="text-[10px] text-slate-500 block mt-0.5">125 kHz LoRa symbol rate</span>
        </div>

        <div className="bg-white border border-slate-200 p-3.5 rounded shadow-xs">
          <span className="text-[10px] text-slate-500 font-semibold uppercase block">Average Packet Latency</span>
          <span className="text-xl font-bold font-mono text-slate-900">
            {net?.avg_latency_ms ?? 0} <span className="text-xs text-slate-500">ms</span>
          </span>
          <span className="text-[10px] text-slate-500 block mt-0.5">
            p95: {net?.p95_latency_ms ?? 0}ms &bull; p99: {net?.p99_latency_ms ?? 0}ms
          </span>
        </div>
      </div>

      {/* Latency Percentiles Card */}
      <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
        <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
          <Cpu className="w-4 h-4 text-[#1B4332]" />
          <span>Detailed Latency Percentiles &amp; Forwarding Queue Telemetry</span>
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="bg-slate-50 p-3 rounded border border-slate-200">
            <span className="text-slate-500 text-[11px] block mb-1">Mean Transmission Airtime</span>
            <span className="text-lg font-bold font-mono text-slate-900">{net?.avg_latency_ms ?? 0} ms</span>
            <p className="text-[10px] text-slate-500 mt-1">LoRa SF9 serialization time at 125 kHz bandwidth</p>
          </div>

          <div className="bg-slate-50 p-3 rounded border border-slate-200">
            <span className="text-slate-500 text-[11px] block mb-1">95th Percentile Delay (p95)</span>
            <span className="text-lg font-bold font-mono text-amber-800">{net?.p95_latency_ms ?? 0} ms</span>
            <p className="text-[10px] text-slate-500 mt-1">Multi-hop store-and-forward relay paths</p>
          </div>

          <div className="bg-slate-50 p-3 rounded border border-slate-200">
            <span className="text-slate-500 text-[11px] block mb-1">Buffered Queue Depth</span>
            <span className="text-lg font-bold font-mono text-slate-900">{net?.queue_depth_total ?? 0} packets</span>
            <p className="text-[10px] text-slate-500 mt-1">Total pending frames across all 5 station buffers</p>
          </div>
        </div>
      </div>

      {/* WPC Compliance & Spectrum Notice */}
      <div className="bg-amber-50 border border-amber-300 p-3.5 rounded text-xs space-y-2">
        <div className="flex items-center gap-2 text-amber-900 font-bold">
          <ShieldAlert className="w-4 h-4 text-amber-700" />
          <span>WPC India Spectrum Compliance Notice (865–867 MHz Band)</span>
        </div>
        <p className="text-amber-950 text-[11px] leading-relaxed">
          {metrics?.disclaimer ||
            'Under Indian Wireless Planning & Coordination (WPC) wing rules, the 865–867 MHz band permits unlicensed low-power transmission up to 1 Watt (30 dBm) ERP for indoor and outdoor operations.'}
        </p>
        <p className="text-amber-900 text-[10px]">
          Physical hardware deployments must operate within WPC Equipment Type Approval (ETA) standards and adhere to carrier sensing and duty-cycle requirements.
        </p>
      </div>
    </div>
  );
};
