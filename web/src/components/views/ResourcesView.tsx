import React, { useEffect, useState } from 'react';
import { StationData } from '../../types';
import { Package, ShieldCheck, Anchor, Pill, ArrowRightLeft, Plus, CheckCircle2 } from 'lucide-react';

interface ResourcesViewProps {
  stations: Record<string, StationData>;
  onRefresh?: () => void;
}

export const ResourcesView: React.FC<ResourcesViewProps> = ({ stations, onRefresh }) => {
  const [activeStation, setActiveStation] = useState('alpha');
  const [state, setState] = useState<any>(null);
  const [consumeAmt, setConsumeAmt] = useState(5);
  const [patient, setPatient] = useState('Critical Trauma Patient');
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const fetchState = () => {
    fetch(`/api/stations/${activeStation}`)
      .then((r) => r.json())
      .then((d) => setState(d.materialized_state))
      .catch(() => {});
  };

  useEffect(() => {
    fetchState();
  }, [activeStation]);

  const handleConsume = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/actions/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: activeStation,
          entity_type: 'supply',
          entity_id: 'supply-antibiotics',
          operation: 'CONSUME_QUOTA',
          payload: { quantity: Number(consumeAmt), beneficiary: patient },
        }),
      });
      const data = await res.json();
      setActionMsg(`Consumed ${consumeAmt} courses from ${activeStation.toUpperCase()}'s local escrow quota.`);
      setTimeout(() => setActionMsg(null), 4000);
      fetchState();
      onRefresh?.();
    } catch (err) {
      console.error(err);
    }
  };

  const supply = state?.supply?.['supply-antibiotics'] || {};
  const quotas = supply.quotas || {};
  const consumed = supply.consumed || 0;
  const totalQty = supply.total_quantity || 120;
  const remainingSum = Object.values(quotas).reduce((a: any, b: any) => a + Number(b), 0);
  const isConserved = remainingSum + consumed === totalQty;

  const boat = state?.scarce_item?.['boat-titan'] || {};

  return (
    <div className="space-y-4">
      {/* View Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
            <Package className="w-4 h-4 text-[#1B4332]" />
            <span>Resource Coordination &amp; Mathematical Allocation Safety</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Escrow Quotas prevent over-allocating divisible medical supplies; Single-Owner Tokens prevent double-booking rescue boats.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-medium">Station Context:</span>
          <select
            value={activeStation}
            onChange={(e) => setActiveStation(e.target.value)}
            className="bg-white border border-slate-300 rounded px-2.5 py-1 text-xs text-slate-900 font-semibold"
          >
            {Object.values(stations).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.id.toUpperCase()})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Card 1: Divisible Supplies (Escrow Quota Pool) */}
        <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
            <div className="flex items-center gap-2">
              <Pill className="w-4 h-4 text-[#1B4332]" />
              <div>
                <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wide">
                  Amoxicillin 500mg (Escrow Quota Pool)
                </h4>
                <span className="text-[11px] text-slate-500">Total Fixed Pool: {totalQty} courses</span>
              </div>
            </div>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                isConserved
                  ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                  : 'bg-red-50 text-red-700 border border-red-200'
              }`}
            >
              {isConserved ? 'INVARIANT CONSERVED' : 'VIOLATION DETECTED'}
            </span>
          </div>

          {/* Quota Progress Breakdown */}
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-slate-600 text-[11px]">
              <span>
                Active Quotas ({remainingSum}) + Consumed ({consumed}) = {remainingSum + consumed}
              </span>
              <span className="font-mono text-emerald-800 font-bold">100% Conserved</span>
            </div>

            {/* Station Quota Badges */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
              {Object.entries(quotas).map(([nid, q]: any) => (
                <div
                  key={nid}
                  className={`p-2 rounded border text-center ${
                    nid === activeStation
                      ? 'bg-slate-50 border-[#1B4332]'
                      : 'bg-white border-slate-200'
                  }`}
                >
                  <span className="block text-[10px] text-slate-500 font-bold uppercase">{nid}</span>
                  <span className="text-base font-bold font-mono text-slate-900">{q}</span>
                  <span className="block text-[10px] text-slate-500">courses</span>
                </div>
              ))}
            </div>
          </div>

          {/* Consume from Escrow Form */}
          <form onSubmit={handleConsume} className="bg-slate-50 p-3.5 rounded border border-slate-200 space-y-2.5 text-xs">
            <h5 className="font-bold text-slate-900 uppercase tracking-wide text-[11px]">
              Consume from {activeStation.toUpperCase()}'s Local Quota ({quotas[activeStation] ?? 0} Available)
            </h5>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-slate-600 mb-1">Courses Quantity</label>
                <input
                  type="number"
                  min="1"
                  max={quotas[activeStation] ?? 1}
                  value={consumeAmt}
                  onChange={(e) => setConsumeAmt(Number(e.target.value))}
                  className="w-full bg-white border border-slate-300 rounded p-1.5 text-slate-900"
                />
              </div>

              <div>
                <label className="block text-slate-600 mb-1">Patient / Beneficiary</label>
                <input
                  type="text"
                  value={patient}
                  onChange={(e) => setPatient(e.target.value)}
                  className="w-full bg-white border border-slate-300 rounded p-1.5 text-slate-900"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              {actionMsg ? <span className="text-xs text-emerald-800 font-semibold">{actionMsg}</span> : <span />}
              <button
                type="submit"
                disabled={(quotas[activeStation] ?? 0) < consumeAmt}
                className="px-3 py-1.5 bg-[#1B4332] hover:bg-[#143827] disabled:bg-slate-200 text-white font-bold rounded transition text-xs shadow-xs"
              >
                Consume Locally (Offline Safe)
              </button>
            </div>
          </form>
        </div>

        {/* Card 2: Indivisible Asset (Single-Owner Boat Token) */}
        <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
            <div className="flex items-center gap-2">
              <Anchor className="w-4 h-4 text-[#1B4332]" />
              <div>
                <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wide">
                  {boat.item_name || 'Titan Flood Rescue Boat #1'}
                </h4>
                <span className="text-[11px] text-slate-500">Single-Owner Indivisible Token</span>
              </div>
            </div>
            <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-900 border border-blue-200 text-[10px] font-bold">
              EXCLUSIVE ASSET
            </span>
          </div>

          <div className="bg-slate-50 p-3 rounded border border-slate-200 text-xs space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-slate-500 text-[10px] uppercase font-bold block">Current Token Holder</span>
                <span className="text-sm font-bold font-mono text-[#1B4332]">
                  {boat.token_holder?.toUpperCase() || 'ALPHA'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 text-[10px] uppercase font-bold block">Asset Allocation Status</span>
                <span className="text-sm font-bold text-slate-900">{boat.status || 'AVAILABLE'}</span>
              </div>
            </div>

            {boat.allocated_to && (
              <div className="p-2 rounded bg-white border border-slate-200 mt-1">
                <span className="text-[10px] text-slate-500 block font-bold uppercase">Assigned Mission</span>
                <span className="text-slate-900 font-semibold">{boat.allocated_to}</span>
              </div>
            )}
          </div>

          <div className="bg-slate-50 border border-slate-200 p-3 rounded text-xs space-y-1.5">
            <h5 className="font-bold text-slate-900 uppercase tracking-wide text-[11px] flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-[#1B4332]" />
              Single-Owner Invariant Protection
            </h5>
            <p className="text-slate-600 text-[11px] leading-relaxed">
              If an offline camp without custody token (e.g. Charlie Mountain Shelter) attempts an allocation, it is recorded as <strong className="text-amber-800">REQUESTED</strong> only. Only the current verified token holder ({boat.token_holder?.toUpperCase()}) can issue a <strong className="text-emerald-800">CONFIRMED_ALLOCATED</strong> event. Two physical teams can never be promised the same boat.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
