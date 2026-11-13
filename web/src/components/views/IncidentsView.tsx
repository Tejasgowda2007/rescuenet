import React, { useState, useEffect } from 'react';
import {
  AlertOctagon,
  Radio,
  Send,
  PlusCircle,
  CheckCircle2,
  Clock,
  Shield,
  MapPin,
  Users,
  Filter,
  RefreshCw,
  AlertTriangle,
  Flame,
  CheckCircle,
  Smartphone,
  Share2,
  MessageSquare,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { offlineStorage, OfflineIncident, OfflineMessage } from '../../services/offlineStorage';
import { getConnectedNearbyPeers, isNearbyMeshAvailable, NearbyPeer } from '../../services/nearbyBridge';

interface IncidentsViewProps {
  onRefresh?: () => void;
}

export const IncidentsView: React.FC<IncidentsViewProps> = ({ onRefresh }) => {
  const { user, apiFetch } = useAuth();
  const [activeTab, setActiveTab] = useState<'incidents' | 'messages'>('incidents');
  
  // Incident State
  const [incidents, setIncidents] = useState<OfflineIncident[]>([]);
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [newTitle, setNewTitle] = useState('');
  const [newCategory, setNewCategory] = useState<'MEDEVAC' | 'COLLAPSE' | 'FIRE' | 'FLOOD' | 'HAZMAT' | 'SUPPLY_DEFICIT'>('MEDEVAC');
  const [newSeverity, setNewSeverity] = useState<'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'>('HIGH');
  const [newLocation, setNewLocation] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newAssignedTeam, setNewAssignedTeam] = useState('Alpha SAR Team 1');
  const [incidentSubmitting, setIncidentSubmitting] = useState(false);
  const [incidentFeedback, setIncidentFeedback] = useState<{ msg: string; type: 'success' | 'warning' | 'error' } | null>(null);

  // Message State
  const [messages, setMessages] = useState<OfflineMessage[]>([]);
  const [msgRecipient, setMsgRecipient] = useState('ALL');
  const [msgPriority, setMsgPriority] = useState<'CRITICAL' | 'HIGH' | 'ROUTINE'>('ROUTINE');
  const [msgContent, setMsgContent] = useState('');
  const [msgSubmitting, setMsgSubmitting] = useState(false);
  const [msgFeedback, setMsgFeedback] = useState<{ msg: string; type: 'success' | 'warning' | 'error' } | null>(null);

  // Connectivity & Nearby State
  const [nearbyPeers, setNearbyPeers] = useState<NearbyPeer[]>([]);
  const [pendingOutboxCount, setPendingOutboxCount] = useState(0);

  // Load Incidents and Messages
  const loadData = async () => {
    // 1. Fetch Incidents: Attempt API first, fallback to IndexedDB
    try {
      const res = await apiFetch('/api/incidents');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const mapped: OfflineIncident[] = data.map((d: any) => ({
            id: d.id || d.incident_id,
            title: d.title,
            category: d.category || 'MEDEVAC',
            severity: d.severity || 'HIGH',
            status: d.status || 'OPEN',
            location: d.location || '',
            description: d.description || '',
            assigned_teams: d.assigned_teams || [],
            reported_by: d.reported_by || 'alpha',
            created_at: d.created_at || d._created_at || Date.now(),
            synced: true,
          }));
          setIncidents(mapped);
          await offlineStorage.saveIncidents(mapped);
        }
      } else {
        throw new Error('API offline');
      }
    } catch {
      // Offline fallback
      const local = await offlineStorage.getIncidents();
      setIncidents(local);
    }

    // 2. Fetch Messages: Attempt API first, fallback to IndexedDB
    try {
      const res = await apiFetch('/api/messages');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const mapped: OfflineMessage[] = data.map((d: any) => ({
            id: d.id || d.message_id,
            sender_id: d.sender_id || 'unknown',
            recipient_id: d.recipient_id || 'ALL',
            content: d.content || '',
            priority: d.priority || 'ROUTINE',
            location: d.location || '',
            timestamp: d.timestamp || d._created_at || Date.now(),
            synced: true,
            status: 'DELIVERED',
          }));
          setMessages(mapped);
          await offlineStorage.saveMessages(mapped);
        }
      } else {
        throw new Error('API offline');
      }
    } catch {
      // Offline fallback
      const local = await offlineStorage.getMessages();
      setMessages(local);
    }

    // 3. Update outbox & nearby peers
    const count = await offlineStorage.getPendingCount();
    setPendingOutboxCount(count);
    setNearbyPeers(getConnectedNearbyPeers());
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);

    // Listen to local window events for immediate reactivity
    const handlePeerData = () => loadData();
    window.addEventListener('rescuenet-peer-data-received', handlePeerData);

    const unsubscribe = offlineStorage.subscribe((cnt) => setPendingOutboxCount(cnt));

    return () => {
      clearInterval(interval);
      window.removeEventListener('rescuenet-peer-data-received', handlePeerData);
      unsubscribe();
    };
  }, []);

  // Submit Incident Handler
  const handleCreateIncident = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    setIncidentSubmitting(true);
    setIncidentFeedback(null);

    const reporter = user?.username || 'field-responder';
    const incidentPayload = {
      title: newTitle.trim(),
      category: newCategory,
      severity: newSeverity,
      status: 'OPEN' as const,
      location: newLocation.trim() || 'Sector Alpha',
      description: newDescription.trim(),
      assigned_teams: newAssignedTeam ? [newAssignedTeam] : [],
      reported_by: reporter,
    };

    try {
      // Try direct API post
      const res = await apiFetch('/api/incidents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(incidentPayload),
      });

      if (res.ok) {
        const result = await res.json();
        setIncidentFeedback({
          msg: `Incident #${result.incident_id || 'NEW'} recorded online to mesh.`,
          type: 'success',
        });
      } else {
        throw new Error(`API HTTP ${res.status}`);
      }
    } catch {
      // Offline mode: store in IndexedDB, queue to outbox, and broadcast via Nearby
      const saved = await offlineStorage.addLocalIncident(incidentPayload);
      setIncidentFeedback({
        msg: `OFFLINE MODE: Incident #${saved.id} saved in local IndexedDB outbox & broadcast to nearby peers.`,
        type: 'warning',
      });
    } finally {
      setIncidentSubmitting(false);
      setNewTitle('');
      setNewLocation('');
      setNewDescription('');
      loadData();
      onRefresh?.();
      setTimeout(() => setIncidentFeedback(null), 5000);
    }
  };

  // Submit Tactical Message Handler
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!msgContent.trim()) return;

    setMsgSubmitting(true);
    setMsgFeedback(null);

    const sender = user?.username || 'alpha';
    const messagePayload = {
      sender_id: sender,
      recipient_id: msgRecipient,
      content: msgContent.trim(),
      priority: msgPriority,
      location: 'Command Post Alpha',
    };

    try {
      // Try direct API post
      const res = await apiFetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(messagePayload),
      });

      if (res.ok) {
        setMsgFeedback({
          msg: `Tactical message transmitted to channel [${msgRecipient}].`,
          type: 'success',
        });
      } else {
        throw new Error(`API HTTP ${res.status}`);
      }
    } catch {
      // Offline mode: store in IndexedDB, queue in outbox, broadcast over Nearby
      const saved = await offlineStorage.addLocalMessage(messagePayload);
      setMsgFeedback({
        msg: `OFFLINE MODE: Message saved locally and queued in outbox for mesh synchronization.`,
        type: 'warning',
      });
    } finally {
      setMsgSubmitting(false);
      setMsgContent('');
      loadData();
      onRefresh?.();
      setTimeout(() => setMsgFeedback(null), 5000);
    }
  };

  // Update Incident Status
  const handleUpdateStatus = async (incidentId: string, nextStatus: string) => {
    try {
      await apiFetch(`/api/incidents/${incidentId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus, resolution_notes: 'Updated via Command Dispatch' }),
      });
    } catch {
      // Update local storage
      const existing = incidents.find((i) => i.id === incidentId);
      if (existing) {
        existing.status = nextStatus as any;
        existing.synced = false;
        await offlineStorage.put('incidents', existing);
        await offlineStorage.queueOutboxAction(`/api/incidents/${incidentId}/status`, 'POST', {
          status: nextStatus,
          resolution_notes: 'Offline update via local operator',
        });
      }
    }
    loadData();
    onRefresh?.();
  };

  // Filtered Incidents
  const filteredIncidents = incidents.filter((inc) => {
    if (severityFilter !== 'ALL' && inc.severity !== severityFilter) return false;
    if (statusFilter !== 'ALL' && inc.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      {/* View Header & Network Sync Status */}
      <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <AlertOctagon className="w-5 h-5 text-[#1B4332]" />
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Disaster Incident Tracking &amp; Tactical Dispatch
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Store-and-forward emergency reporting with automatic offline queueing and Google Nearby P2P mesh broadcasting.
          </p>
        </div>

        {/* Status Indicators */}
        <div className="flex items-center gap-3">
          {/* Nearby Mesh Indicator */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700">
            <Smartphone className="w-3.5 h-3.5 text-blue-600" />
            <span>
              Nearby P2P:{' '}
              <strong className="text-slate-900">
                {isNearbyMeshAvailable() ? `${nearbyPeers.length} Peer(s)` : 'LAN Fallback'}
              </strong>
            </span>
          </div>

          {/* Outbox Pending Indicator */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border text-xs font-semibold ${
              pendingOutboxCount > 0
                ? 'bg-amber-50 border-amber-300 text-amber-800'
                : 'bg-emerald-50 border-emerald-300 text-emerald-800'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Outbox: {pendingOutboxCount} pending</span>
          </div>

          {/* Refresh Button */}
          <button
            onClick={loadData}
            className="p-1.5 rounded border border-slate-200 hover:bg-slate-100 text-slate-600 transition"
            title="Refresh Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b border-slate-200 bg-white px-4 rounded-t-lg">
        <button
          onClick={() => setActiveTab('incidents')}
          className={`py-3 px-4 text-xs font-bold uppercase tracking-wider border-b-2 flex items-center gap-2 transition ${
            activeTab === 'incidents'
              ? 'border-[#1B4332] text-[#1B4332]'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <AlertOctagon className="w-4 h-4" />
          <span>Incident Reports ({incidents.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('messages')}
          className={`py-3 px-4 text-xs font-bold uppercase tracking-wider border-b-2 flex items-center gap-2 transition ${
            activeTab === 'messages'
              ? 'border-[#1B4332] text-[#1B4332]'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          <span>Tactical Radio Dispatch ({messages.length})</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: INCIDENT REPORTS & CREATION */}
      {/* ========================================================================= */}
      {activeTab === 'incidents' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Left Column: Report Incident Form (1 col) */}
          <div className="lg:col-span-1 bg-white p-4 rounded-lg border border-slate-200 shadow-xs space-y-4">
            <div className="border-b border-slate-100 pb-2">
              <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <PlusCircle className="w-4 h-4 text-[#1B4332]" />
                <span>Log New Disaster Incident</span>
              </h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Automatically cryptographically stamped with Ed25519 signature &amp; cached locally.
              </p>
            </div>

            {incidentFeedback && (
              <div
                className={`p-2.5 rounded text-xs font-medium border ${
                  incidentFeedback.type === 'success'
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                    : incidentFeedback.type === 'warning'
                    ? 'bg-amber-50 border-amber-300 text-amber-800'
                    : 'bg-red-50 border-red-300 text-red-800'
                }`}
              >
                {incidentFeedback.msg}
              </div>
            )}

            <form onSubmit={handleCreateIncident} className="space-y-3">
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                  Incident Title *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Flash Flood Trapping 4 Hikers"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded focus:border-[#1B4332] focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                    Category
                  </label>
                  <select
                    value={newCategory}
                    onChange={(e: any) => setNewCategory(e.target.value)}
                    className="w-full text-xs px-2 py-1.5 border border-slate-300 rounded bg-white"
                  >
                    <option value="MEDEVAC">MEDEVAC</option>
                    <option value="COLLAPSE">COLLAPSE</option>
                    <option value="FIRE">WILDFIRE</option>
                    <option value="FLOOD">FLASH FLOOD</option>
                    <option value="HAZMAT">HAZMAT</option>
                    <option value="SUPPLY_DEFICIT">SUPPLY SHORTAGE</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                    Severity
                  </label>
                  <select
                    value={newSeverity}
                    onChange={(e: any) => setNewSeverity(e.target.value)}
                    className="w-full text-xs px-2 py-1.5 border border-slate-300 rounded bg-white font-semibold text-slate-900"
                  >
                    <option value="CRITICAL">P0 - CRITICAL</option>
                    <option value="HIGH">P1 - HIGH</option>
                    <option value="MEDIUM">P2 - MEDIUM</option>
                    <option value="LOW">P3 - LOW</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                  Location / Sector
                </label>
                <input
                  type="text"
                  placeholder="e.g. Trishul Pass Ridge Km 14"
                  value={newLocation}
                  onChange={(e) => setNewLocation(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded focus:border-[#1B4332] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                  Assign Emergency Team
                </label>
                <select
                  value={newAssignedTeam}
                  onChange={(e) => setNewAssignedTeam(e.target.value)}
                  className="w-full text-xs px-2 py-1.5 border border-slate-300 rounded bg-white"
                >
                  <option value="Alpha Medical Unit 1">Alpha Medical Unit 1</option>
                  <option value="Beta Field Triage Team">Beta Field Triage Team</option>
                  <option value="Charlie High-Pass SAR">Charlie High-Pass SAR</option>
                  <option value="Delta Evac Transport Squad">Delta Evac Transport Squad</option>
                  <option value="Echo Logistics Convoy">Echo Logistics Convoy</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                  Situation Details
                </label>
                <textarea
                  rows={2}
                  placeholder="Key observations, medical needs, access obstacles..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded focus:border-[#1B4332] focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={incidentSubmitting}
                className="w-full bg-[#1B4332] text-white py-2 rounded text-xs font-bold uppercase tracking-wider hover:bg-[#143326] transition disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                {incidentSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Transmitting...</span>
                  </>
                ) : (
                  <>
                    <AlertOctagon className="w-3.5 h-3.5" />
                    <span>Dispatch Incident</span>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Right Column: Incidents Ledger & Action Table (2 cols) */}
          <div className="lg:col-span-2 space-y-3">
            {/* Filter Bar */}
            <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                <Filter className="w-3.5 h-3.5 text-slate-500" />
                <span className="font-bold text-slate-700 uppercase tracking-wider text-[11px]">Filters:</span>
                
                <select
                  value={severityFilter}
                  onChange={(e) => setSeverityFilter(e.target.value)}
                  className="border border-slate-300 rounded px-2 py-1 bg-white text-xs font-medium"
                >
                  <option value="ALL">All Severities</option>
                  <option value="CRITICAL">Critical Only</option>
                  <option value="HIGH">High</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="LOW">Low</option>
                </select>

                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="border border-slate-300 rounded px-2 py-1 bg-white text-xs font-medium"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="OPEN">Open</option>
                  <option value="ASSIGNED">Assigned</option>
                  <option value="RESOLVED">Resolved</option>
                </select>
              </div>

              <span className="text-[11px] text-slate-500">
                Displaying <strong>{filteredIncidents.length}</strong> incident(s)
              </span>
            </div>

            {/* Incidents List */}
            {filteredIncidents.length === 0 ? (
              <div className="bg-white p-8 rounded-lg border border-slate-200 text-center text-slate-400 text-xs">
                No disaster incidents logged matching current filters.
              </div>
            ) : (
              <div className="space-y-2">
                {filteredIncidents.map((inc) => {
                  const isCritical = inc.severity === 'CRITICAL';
                  const isHigh = inc.severity === 'HIGH';
                  const isResolved = inc.status === 'RESOLVED';

                  return (
                    <div
                      key={inc.id}
                      className={`p-3.5 rounded-lg border bg-white shadow-xs transition ${
                        isResolved
                          ? 'border-slate-200 opacity-70'
                          : isCritical
                          ? 'border-red-300 bg-red-50/20'
                          : isHigh
                          ? 'border-amber-300'
                          : 'border-slate-200'
                      }`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                                isCritical
                                  ? 'bg-red-600 text-white'
                                  : isHigh
                                  ? 'bg-amber-600 text-white'
                                  : 'bg-slate-600 text-white'
                              }`}
                            >
                              {inc.severity}
                            </span>

                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 uppercase">
                              {inc.category}
                            </span>

                            <span className="font-bold text-xs text-slate-900">{inc.title}</span>
                          </div>

                          <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3 h-3 text-slate-400" />
                              {inc.location || 'Unknown Sector'}
                            </span>

                            <span className="flex items-center gap-1">
                              <Users className="w-3 h-3 text-slate-400" />
                              Reporter: {inc.reported_by}
                            </span>

                            <span>{new Date(inc.created_at).toLocaleTimeString()}</span>
                          </div>

                          {inc.description && (
                            <p className="text-xs text-slate-600 mt-1">{inc.description}</p>
                          )}

                          {inc.assigned_teams && inc.assigned_teams.length > 0 && (
                            <div className="text-[11px] text-slate-700 font-medium">
                              Assigned: <span className="text-blue-800">{inc.assigned_teams.join(', ')}</span>
                            </div>
                          )}
                        </div>

                        {/* Status & Actions */}
                        <div className="flex flex-col items-end gap-2">
                          <div className="flex items-center gap-1.5">
                            {inc.synced ? (
                              <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                                <CheckCircle className="w-3 h-3" /> Synced
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                                <Clock className="w-3 h-3" /> Outbox Queued
                              </span>
                            )}

                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                isResolved
                                  ? 'bg-slate-200 text-slate-700'
                                  : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              {inc.status}
                            </span>
                          </div>

                          {/* Action Buttons */}
                          {!isResolved && (
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => handleUpdateStatus(inc.id, 'RESOLVED')}
                                className="px-2 py-1 text-[11px] font-semibold bg-emerald-600 text-white rounded hover:bg-emerald-700 transition"
                              >
                                Mark Resolved
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: TACTICAL RADIO & PEER MESSAGING */}
      {/* ========================================================================= */}
      {activeTab === 'messages' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Left Column: Dispatch Tactical Message Form (1 col) */}
          <div className="lg:col-span-1 bg-white p-4 rounded-lg border border-slate-200 shadow-xs space-y-4">
            <div className="border-b border-slate-100 pb-2">
              <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <Radio className="w-4 h-4 text-[#1B4332]" />
                <span>Transmit Tactical Radio Message</span>
              </h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Simulated 868 MHz LoRa packet framing + direct Android Nearby wireless broadcast.
              </p>
            </div>

            {msgFeedback && (
              <div
                className={`p-2.5 rounded text-xs font-medium border ${
                  msgFeedback.type === 'success'
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                    : msgFeedback.type === 'warning'
                    ? 'bg-amber-50 border-amber-300 text-amber-800'
                    : 'bg-red-50 border-red-300 text-red-800'
                }`}
              >
                {msgFeedback.msg}
              </div>
            )}

            <form onSubmit={handleSendMessage} className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                    Channel / Recipient
                  </label>
                  <select
                    value={msgRecipient}
                    onChange={(e) => setMsgRecipient(e.target.value)}
                    className="w-full text-xs px-2 py-1.5 border border-slate-300 rounded bg-white font-semibold"
                  >
                    <option value="ALL">ALL (Broadcast)</option>
                    <option value="alpha">Alpha — Harbor Command</option>
                    <option value="beta">Beta — Hospital Triage</option>
                    <option value="charlie">Charlie — High Pass</option>
                    <option value="delta">Delta — Supply Depot</option>
                    <option value="echo">Echo — Ridge Relay</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                    Priority
                  </label>
                  <select
                    value={msgPriority}
                    onChange={(e: any) => setMsgPriority(e.target.value)}
                    className="w-full text-xs px-2 py-1.5 border border-slate-300 rounded bg-white font-semibold text-slate-900"
                  >
                    <option value="CRITICAL">P0 - FLASH SOS</option>
                    <option value="HIGH">P1 - PRIORITY</option>
                    <option value="ROUTINE">P2 - ROUTINE</option>
                  </select>
                </div>
              </div>

              {/* Quick Template Chips */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                  Tactical Quick Templates
                </label>
                <div className="flex flex-wrap gap-1">
                  {[
                    'Requesting urgent triage medevac at Sector Charlie.',
                    'Ridge pass blocked by landslide. Re-routing via Echo.',
                    'Supply convoy arrived at Delta depot with medical crates.',
                    'Repeater running on backup battery (76%). Link healthy.',
                  ].map((tpl, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setMsgContent(tpl)}
                      className="text-[10px] bg-slate-100 hover:bg-slate-200 text-slate-700 px-2 py-0.5 rounded text-left transition border border-slate-200"
                    >
                      {tpl}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-600 mb-1">
                  Message Body *
                </label>
                <textarea
                  required
                  rows={3}
                  placeholder="Enter emergency transmission..."
                  value={msgContent}
                  onChange={(e) => setMsgContent(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded focus:border-[#1B4332] focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={msgSubmitting}
                className="w-full bg-[#1B4332] text-white py-2 rounded text-xs font-bold uppercase tracking-wider hover:bg-[#143326] transition disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                {msgSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Broadcasting Packet...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Transmit Packet</span>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Right Column: Message Transmission Stream (2 cols) */}
          <div className="lg:col-span-2 space-y-3">
            <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs flex items-center justify-between text-xs">
              <span className="font-bold text-slate-700 uppercase tracking-wider text-[11px]">
                Radio Packet Stream ({messages.length} messages received)
              </span>
              <span className="text-[11px] text-slate-500">
                Sorted chronologically by event timestamp
              </span>
            </div>

            {messages.length === 0 ? (
              <div className="bg-white p-8 rounded-lg border border-slate-200 text-center text-slate-400 text-xs">
                No tactical radio transmissions on record yet. Compose a message above to transmit.
              </div>
            ) : (
              <div className="space-y-2">
                {messages.map((m) => {
                  const isFlash = m.priority === 'CRITICAL';
                  const isHigh = m.priority === 'HIGH';

                  return (
                    <div
                      key={m.id}
                      className={`p-3 rounded-lg border bg-white shadow-xs ${
                        isFlash
                          ? 'border-red-300 bg-red-50/25'
                          : isHigh
                          ? 'border-amber-300'
                          : 'border-slate-200'
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-1.5 mb-1.5 text-[11px]">
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-[9px] font-bold px-1.5 py-0.2 rounded uppercase ${
                              isFlash
                                ? 'bg-red-600 text-white'
                                : isHigh
                                ? 'bg-amber-600 text-white'
                                : 'bg-slate-600 text-white'
                            }`}
                          >
                            {m.priority}
                          </span>

                          <span className="font-bold text-slate-800">
                            FROM: <strong className="text-[#1B4332]">{m.sender_id}</strong> &rarr; TO: <strong className="text-blue-700">{m.recipient_id}</strong>
                          </span>
                        </div>

                        <div className="flex items-center gap-2 text-slate-400 text-[10px]">
                          <span>{new Date(m.timestamp).toLocaleTimeString()}</span>
                          <span className="font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                            {m.status || 'DELIVERED'}
                          </span>
                        </div>
                      </div>

                      <p className="text-xs text-slate-800 font-mono whitespace-pre-wrap">{m.content}</p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
