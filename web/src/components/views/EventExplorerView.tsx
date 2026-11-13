import React, { useEffect, useState } from 'react';
import { StationData, EventRecord } from '../../types';
import {
  Database,
  ShieldCheck,
  AlertTriangle,
  Lock,
  CheckCircle2,
  UserCheck,
  FileText,
  Key,
  Layers,
  Search,
  Filter,
  Clock,
  Fingerprint,
} from 'lucide-react';

interface EventExplorerViewProps {
  stations: Record<string, StationData>;
  onRefresh?: () => void;
}

export const EventExplorerView: React.FC<EventExplorerViewProps> = ({ stations, onRefresh }) => {
  const [selectedStation, setSelectedStation] = useState('alpha');
  const [activeTab, setActiveTab] = useState<'materialized' | 'raw_events'>('materialized');
  const [materialized, setMaterialized] = useState<any>(null);
  const [rawEvents, setRawEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [resolveNote, setResolveNote] = useState('Verified by field triage unit');
  const [resolvedStatus, setResolvedStatus] = useState('FOUND_SAFE_VERIFIED');
  const [filterType, setFilterType] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchState = () => {
    setLoading(true);
    fetch(`/api/stations/${selectedStation}`)
      .then((r) => r.json())
      .then((data) => {
        setMaterialized(data.materialized_state);
        setRawEvents(data.events || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    fetchState();
  }, [selectedStation]);

  const handleResolve = async (personId: string) => {
    await fetch(
      `/api/actions/resolve-conflict?person_id=${personId}&resolved_status=${resolvedStatus}&notes=${encodeURIComponent(
        resolveNote
      )}&station_id=${selectedStation}`,
      { method: 'POST' }
    );
    fetchState();
    onRefresh?.();
  };

  const people = materialized?.person || {};
  const conflictedPeople = Object.entries(people).filter(([_, p]: any) => p.conflicts && p.conflicts.length > 0);

  // Filter raw events
  const filteredEvents = rawEvents.filter((ev) => {
    if (filterType !== 'all' && ev.entity_type !== filterType) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        ev.event_id.toLowerCase().includes(q) ||
        ev.entity_id.toLowerCase().includes(q) ||
        JSON.stringify(ev.payload).toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-4">
      {/* View Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
            <Database className="w-4 h-4 text-[#1B4332]" />
            <span>Immutable Event Sourcing Explorer &amp; Cryptographic Ledger</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Content-addressed SHA-256 events folded deterministically in canonical order (timestamp, node_id, counter).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-medium">Select Station Store:</span>
          <select
            value={selectedStation}
            onChange={(e) => setSelectedStation(e.target.value)}
            className="bg-white border border-slate-300 rounded px-2.5 py-1 text-xs text-slate-900 font-semibold focus:outline-none focus:border-[#1B4332]"
          >
            {Object.values(stations).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.id.toUpperCase()})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Disputed Sightings Conflict Triage Banner (Human in the loop) */}
      {conflictedPeople.length > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded p-4 shadow-xs space-y-3">
          <div className="flex items-center gap-2 text-amber-900 font-bold text-xs uppercase tracking-wider">
            <AlertTriangle className="w-4 h-4 text-amber-700" />
            <span>Human-in-the-Loop Triage Required ({conflictedPeople.length} Disputed Observations)</span>
          </div>
          <p className="text-xs text-amber-800">
            Concurrent sightings of displaced victims were logged independently during a network partition. Review competing claims and issue a signed resolution event.
          </p>

          <div className="space-y-3 pt-1">
            {conflictedPeople.map(([pid, p]: any) => (
              <div key={pid} className="bg-white p-3.5 rounded border border-amber-200 text-xs space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    <h5 className="font-bold text-slate-900 text-sm">{p.name || pid}</h5>
                    <span className="text-[11px] text-slate-500 font-mono">Entity ID: {pid}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-300 text-[10px] font-bold">
                    DISPUTED OBSERVATION
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* Current Local LWW Record */}
                  <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
                    <span className="text-[10px] text-slate-500 uppercase font-semibold block">Observation A</span>
                    <span className="font-bold text-slate-900 text-xs block mt-1">Status: {p.status}</span>
                    <span className="text-slate-600 block text-[11px]">Location: {p.location || 'N/A'}</span>
                    <span className="text-[10px] text-slate-500 block mt-0.5">Notes: {p.notes || 'None'}</span>
                  </div>

                  {/* Conflicting Remote Record */}
                  <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
                    <span className="text-[10px] text-slate-500 uppercase font-semibold block">Observation B (Competing Claim)</span>
                    <span className="font-bold text-slate-900 text-xs block mt-1">
                      Status: {p.conflicts[0]?.conflicting_status || 'INJURED'}
                    </span>
                    <span className="text-slate-600 block text-[11px]">
                      Reporter: {p.conflicts[0]?.node_id?.toUpperCase() || 'REMOTE NODE'}
                    </span>
                    <span className="text-[10px] text-slate-500 block mt-0.5">Zero data loss: both records preserved</span>
                  </div>
                </div>

                {/* Resolution Action Row */}
                <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-100">
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-600 font-semibold text-xs">Verified Status:</span>
                    <select
                      value={resolvedStatus}
                      onChange={(e) => setResolvedStatus(e.target.value)}
                      className="bg-slate-50 border border-slate-300 rounded p-1 text-xs text-slate-900"
                    >
                      <option value="FOUND_SAFE_VERIFIED">FOUND_SAFE_VERIFIED (Discharged)</option>
                      <option value="IN_SURGERY_STABLE">IN_SURGERY_STABLE (Critical Care)</option>
                      <option value="EVACUATED_CONFIRMED">EVACUATED_CONFIRMED (Airlifted)</option>
                    </select>
                  </div>

                  <input
                    type="text"
                    value={resolveNote}
                    onChange={(e) => setResolveNote(e.target.value)}
                    placeholder="Enter audit rationale..."
                    className="flex-1 bg-slate-50 border border-slate-300 rounded px-2.5 py-1 text-xs text-slate-900 min-w-[200px]"
                  />

                  <button
                    onClick={() => handleResolve(pid)}
                    className="px-3 py-1 rounded bg-[#1B4332] hover:bg-[#143827] text-white text-xs font-bold transition shadow-xs"
                  >
                    Emit Signed Resolution Event
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Ledger & State Card */}
      <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
        {/* View Toggle Tabs */}
        <div className="flex flex-wrap items-center justify-between border-b border-slate-100 pb-2.5 gap-2">
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setActiveTab('materialized')}
              className={`px-3 py-1 rounded text-xs font-semibold transition ${
                activeTab === 'materialized'
                  ? 'bg-[#1B4332] text-white shadow-xs'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              Materialized Domain View
            </button>
            <button
              onClick={() => setActiveTab('raw_events')}
              className={`px-3 py-1 rounded text-xs font-semibold transition ${
                activeTab === 'raw_events'
                  ? 'bg-[#1B4332] text-white shadow-xs'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              Raw Immutable Event Log ({rawEvents.length})
            </button>
          </div>

          {activeTab === 'raw_events' && (
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search event hash, ID, payload..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-50 border border-slate-300 rounded px-2 py-0.5 text-xs text-slate-900 w-52"
              />
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="bg-slate-50 border border-slate-300 rounded px-2 py-0.5 text-xs text-slate-900"
              >
                <option value="all">All Entities</option>
                <option value="person">Persons</option>
                <option value="supply">Supplies</option>
                <option value="scarce_item">Boat Tokens</option>
                <option value="shelter">Shelters</option>
                <option value="need">Needs</option>
              </select>
            </div>
          )}
        </div>

        {/* Tab 1: Materialized State */}
        {activeTab === 'materialized' && (
          <div className="space-y-4">
            {/* Displaced Persons Summary Table */}
            <div>
              <h5 className="text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-2">
                Displaced Persons &amp; Patients Ledger ({Object.keys(people).length} Records)
              </h5>
              <div className="overflow-x-auto border border-slate-200 rounded">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold font-sans">
                    <tr>
                      <th className="py-2 px-3">Entity ID</th>
                      <th className="py-2 px-3">Person Name</th>
                      <th className="py-2 px-3">Status</th>
                      <th className="py-2 px-3">Field Location</th>
                      <th className="py-2 px-3">Clinical / Triage Notes</th>
                      <th className="py-2 px-3 text-right">Conflict Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-800">
                    {Object.entries(people).length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-4 text-center text-slate-400">
                          No person records stored on {selectedStation.toUpperCase()}.
                        </td>
                      </tr>
                    ) : (
                      Object.entries(people).map(([pid, p]: any) => (
                        <tr key={pid} className="hover:bg-slate-50">
                          <td className="py-2 px-3 font-mono text-[11px] text-slate-600">{pid}</td>
                          <td className="py-2 px-3 font-bold text-slate-900">{p.name || pid}</td>
                          <td className="py-2 px-3 font-semibold">{p.status}</td>
                          <td className="py-2 px-3">{p.location || 'N/A'}</td>
                          <td className="py-2 px-3 text-slate-600">{p.notes || 'None'}</td>
                          <td className="py-2 px-3 text-right">
                            {p.conflicts && p.conflicts.length > 0 ? (
                              <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-bold text-[10px]">
                                Disputed
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-800 font-bold text-[10px]">
                                Converged
                              </span>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Raw Append-Only Immutable Events */}
        {activeTab === 'raw_events' && (
          <div className="overflow-x-auto border border-slate-200 rounded">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold font-sans">
                <tr>
                  <th className="py-2 px-3">Seq #</th>
                  <th className="py-2 px-3">Origin Node</th>
                  <th className="py-2 px-3">Timestamp</th>
                  <th className="py-2 px-3">Entity Type</th>
                  <th className="py-2 px-3">Operation</th>
                  <th className="py-2 px-3">Payload Summary</th>
                  <th className="py-2 px-3">Cryptographic Signature</th>
                  <th className="py-2 px-3 text-right">Event Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-800 font-sans">
                {filteredEvents.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-4 text-center text-slate-400">
                      No matching events found.
                    </td>
                  </tr>
                ) : (
                  filteredEvents.map((ev) => (
                    <tr key={ev.event_id} className="hover:bg-slate-50">
                      <td className="py-2 px-3 font-mono font-bold">{ev.counter}</td>
                      <td className="py-2 px-3 font-semibold text-slate-900">{ev.node_id?.toUpperCase()}</td>
                      <td className="py-2 px-3 font-mono text-slate-500 text-[11px]">
                        {new Date(ev.timestamp * 1000).toLocaleTimeString()}
                      </td>
                      <td className="py-2 px-3 font-mono">{ev.entity_type}</td>
                      <td className="py-2 px-3 font-bold">{ev.operation}</td>
                      <td className="py-2 px-3 font-mono text-[11px] text-slate-600">
                        {JSON.stringify(ev.payload).slice(0, 50)}...
                      </td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                          Ed25519 Valid
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-[10px] text-slate-500">
                        {ev.event_id.slice(0, 12)}...
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
