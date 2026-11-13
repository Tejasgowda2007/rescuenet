import React, { useState } from 'react';
import { StationData } from '../../types';
import { Building2, Battery, Database, Plus, Check, AlertOctagon, Radio, Power, Server } from 'lucide-react';

interface StationsViewProps {
  stations: Record<string, StationData>;
  onRefresh?: () => void;
}

export const StationsView: React.FC<StationsViewProps> = ({ stations, onRefresh }) => {
  const [selectedId, setSelectedId] = useState<string>('alpha');
  const [entityType, setEntityType] = useState<string>('person');
  const [nameOrItem, setNameOrItem] = useState<string>('Ravi Kumar');
  const [statusOrUrgency, setStatusOrUrgency] = useState<string>('INJURED');
  const [location, setLocation] = useState<string>('Valley Pier #2');
  const [logSuccess, setLogSuccess] = useState<string | null>(null);

  const selected = stations[selectedId] || Object.values(stations)[0];

  const handleLogEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;

    const payload: Record<string, any> = {
      name: nameOrItem,
      status: statusOrUrgency,
      location: location,
    };
    if (entityType === 'need') {
      payload.item = nameOrItem;
      payload.urgency = statusOrUrgency;
    }

    try {
      const res = await fetch('/api/actions/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: selected.id,
          entity_type: entityType,
          entity_id: `${entityType}-${nameOrItem.toLowerCase().replace(/\s+/g, '-')}`,
          operation: 'UPDATE',
          payload,
        }),
      });
      const data = await res.json();
      setLogSuccess(`Recorded locally in ${selected.name}'s SQLite store (Sequence #${data.counter})`);
      setTimeout(() => setLogSuccess(null), 4000);
      onRefresh?.();
    } catch (err) {
      console.error(err);
    }
  };

  const handleStatusChange = async (stnId: string, newStatus: string) => {
    await fetch(`/api/stations/${stnId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
    onRefresh?.();
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
          <Building2 className="w-4 h-4 text-[#1B4332]" />
          <span>Station Fleet Management &amp; Local SQLite Stores</span>
        </h3>
        <p className="text-xs text-slate-500 mt-0.5">
          Each station maintains an independent SQLite database, logical vector clock, and solar battery subsystem.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left Column: Station Selector List */}
        <div className="space-y-2">
          {Object.values(stations).map((stn) => {
            const isSelected = stn.id === selectedId;
            const isOnline = stn.status === 'ONLINE';
            const isDegraded = stn.status === 'DEGRADED';
            const isPhysical = stn.id === 'alpha';

            return (
              <div
                key={stn.id}
                onClick={() => setSelectedId(stn.id)}
                className={`p-3 rounded border transition cursor-pointer flex items-center justify-between ${
                  isSelected
                    ? 'bg-white border-[#1B4332] shadow-sm'
                    : 'bg-white border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        isOnline ? 'bg-emerald-600' : isDegraded ? 'bg-amber-500' : 'bg-red-600'
                      }`}
                    />
                    <span className="font-bold text-xs text-slate-900">{stn.name}</span>
                  </div>
                  <span className="text-[11px] text-slate-500 block mt-0.5">
                    {stn.role.split('&')[0]} &bull; {stn.elevation_m}m
                  </span>
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
                    Bat: {stn.battery_pct}% &bull; {stn.events_count} ev
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right 2 Columns: Selected Station Detail & Event Logger */}
        {selected && (
          <div className="lg:col-span-2 space-y-4">
            {/* Station Status & Specs Card */}
            <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${
                        selected.status === 'ONLINE' ? 'bg-emerald-600' : 'bg-amber-500'
                      }`}
                    />
                    <h4 className="text-sm font-bold text-[#0F172A]">{selected.name}</h4>
                    <span className="text-[10px] font-mono font-bold bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200">
                      NODE {selected.id.toUpperCase()}
                    </span>
                    <span className="text-[10px] font-mono font-semibold bg-emerald-50 text-emerald-800 px-1.5 py-0.5 rounded border border-emerald-200">
                      {selected.id === 'alpha' ? 'PHYSICAL BASE' : 'SIMULATED LORA STUB'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {selected.role} &bull; Coordinates: [{selected.coords[0]} km, {selected.coords[1]} km]
                  </p>
                </div>

                {/* Power / Status Switcher */}
                <div className="flex items-center gap-1.5">
                  {['ONLINE', 'DEGRADED', 'POWER_DEPLETED'].map((st) => (
                    <button
                      key={st}
                      onClick={() => handleStatusChange(selected.id, st)}
                      className={`px-2 py-1 rounded text-[10px] font-bold border transition ${
                        selected.status === st
                          ? 'bg-[#1B4332] text-white border-[#1B4332]'
                          : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>

              {/* Hardware & Storage Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <span className="text-[10px] text-slate-500 block">Battery Level</span>
                  <span className="text-base font-bold font-mono text-slate-900">{selected.battery_pct}%</span>
                  <span className="text-[10px] text-slate-600 block">{selected.battery_wh} Wh capacity</span>
                </div>

                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <span className="text-[10px] text-slate-500 block">Elevation &amp; Mast</span>
                  <span className="text-base font-bold font-mono text-slate-900">{selected.elevation_m} m</span>
                  <span className="text-[10px] text-slate-600 block">Mast: {selected.antenna_mast_m} m</span>
                </div>

                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <span className="text-[10px] text-slate-500 block">Local SQLite Events</span>
                  <span className="text-base font-bold font-mono text-emerald-800">{selected.events_count}</span>
                  <span className="text-[10px] text-slate-600 block">Immutable records</span>
                </div>

                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <span className="text-[10px] text-slate-500 block">Radio Channel</span>
                  <span className="text-[11px] font-bold font-mono text-slate-900 mt-1 block">
                    865–867 MHz LoRa
                  </span>
                  <span className="text-[10px] text-slate-600 block">WPC India ISM</span>
                </div>
              </div>
            </div>

            {/* Offline Event Emission Form */}
            <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                <div className="flex items-center gap-2">
                  <Plus className="w-4 h-4 text-[#1B4332]" />
                  <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                    Log Field Observation on {selected.name}
                  </h4>
                </div>
                <span className="text-[11px] text-slate-500">
                  Appends signed event locally without requiring internet
                </span>
              </div>

              {logSuccess && (
                <div className="p-2.5 bg-emerald-50 border border-emerald-300 text-emerald-900 rounded text-xs font-semibold">
                  {logSuccess}
                </div>
              )}

              <form onSubmit={handleLogEvent} className="space-y-3 text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Entity Type</label>
                    <select
                      value={entityType}
                      onChange={(e) => setEntityType(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-slate-900"
                    >
                      <option value="person">Displaced Person / Patient</option>
                      <option value="need">Emergency Resource Need</option>
                      <option value="shelter">Shelter Facility</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Name / Item Description</label>
                    <input
                      type="text"
                      value={nameOrItem}
                      onChange={(e) => setNameOrItem(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-slate-900"
                    />
                  </div>

                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Triage Status / Urgency</label>
                    <select
                      value={statusOrUrgency}
                      onChange={(e) => setStatusOrUrgency(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-slate-900"
                    >
                      <option value="INJURED">INJURED (Urgent Care)</option>
                      <option value="FOUND_SAFE">FOUND_SAFE (Stable)</option>
                      <option value="MISSING">MISSING (Unaccounted)</option>
                      <option value="CRITICAL">CRITICAL</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-slate-700 font-medium mb-1">Observed Field Location</label>
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-slate-900"
                  />
                </div>

                <div className="flex justify-end pt-1">
                  <button
                    type="submit"
                    className="px-3.5 py-1.5 rounded bg-[#1B4332] hover:bg-[#143827] text-white font-bold text-xs shadow-xs transition"
                  >
                    Append to Local Event Store
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
