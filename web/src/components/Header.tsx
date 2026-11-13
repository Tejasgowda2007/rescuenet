import React, { useState } from 'react';
import { Radio, Play, Pause, AlertOctagon, Award, ShieldAlert, Wifi, WifiOff, LogOut, UserCircle } from 'lucide-react';
import { LiveMetrics } from '../types';
import { useAuth } from '../context/AuthContext';

interface HeaderProps {
  metrics: LiveMetrics | null;
  onOpenDemo: () => void;
  onTriggerSOS: (msg: string) => void;
  activeScenarioName?: string;
}

export const Header: React.FC<HeaderProps> = ({
  metrics,
  onOpenDemo,
  onTriggerSOS,
  activeScenarioName = 'Normal Operations (Baseline)',
}) => {
  const { user, logout } = useAuth();
  const [isPlaying, setIsPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [sosModal, setSosModal] = useState(false);
  const [sosText, setSosText] = useState('Immediate medical airlift required in Sector Charlie');

  const togglePlay = () => {
    const next = !isPlaying;
    setIsPlaying(next);
    fetch('/api/simulation/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: next ? 'play' : 'pause' }),
    });
  };

  const handleSpeed = (s: number) => {
    setSpeed(s);
    fetch('/api/simulation/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set_speed', speed: s }),
    });
  };

  const handleSendSOS = () => {
    onTriggerSOS(sosText);
    setSosModal(false);
  };

  const isPartitioned = metrics?.network.is_partitioned ?? false;
  const islandsCount = metrics?.network.connected_islands ?? 1;

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40 px-4 sm:px-6 py-2.5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Brand & System Identity */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded bg-[#1B4332] text-white flex items-center justify-center font-bold shadow-sm">
            <Radio className="w-5 h-5 text-emerald-200" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold tracking-wider text-[#0F172A] font-sans">
                RESCUENET <span className="text-[#1B4332]">FIELDMESH</span>
              </span>
              <span className="text-[10px] font-mono font-semibold bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-300">
                EOC v2.0
              </span>
              <span className="text-[10px] font-mono text-slate-500 hidden md:inline">
                LoRa 865–867 MHz
              </span>
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Decentralized Emergency Response Operations Platform
            </p>
          </div>
        </div>

        {/* Network State Pill & Active Scenario */}
        <div className="flex items-center gap-2.5">
          {isPartitioned ? (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-red-50 border border-red-200 text-red-800 text-xs font-semibold">
              <WifiOff className="w-3.5 h-3.5 text-red-600" />
              <span>Network Partitioned ({islandsCount} Islands)</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs font-semibold">
              <Wifi className="w-3.5 h-3.5 text-[#1B4332]" />
              <span>Mesh Connected (Full Coverage)</span>
            </div>
          )}

          <div className="hidden lg:flex items-center gap-1.5 px-2 py-1 rounded bg-slate-50 border border-slate-200 text-slate-600 text-xs">
            <span className="text-slate-400 font-medium">Scenario:</span>
            <span className="font-semibold text-slate-800">{activeScenarioName}</span>
          </div>
        </div>

        {/* Simulation Clock Controls & Emergency Actions */}
        <div className="flex items-center gap-2">
          {/* Simulation Time / Controls */}
          <div className="flex items-center bg-slate-100 border border-slate-200 rounded p-0.5">
            <button
              onClick={togglePlay}
              className="p-1 rounded hover:bg-white text-slate-700 transition"
              title={isPlaying ? 'Pause Simulation' : 'Resume Simulation'}
            >
              {isPlaying ? <Pause className="w-3.5 h-3.5 text-[#1B4332]" /> : <Play className="w-3.5 h-3.5 text-amber-600" />}
            </button>
            <div className="h-3.5 w-px bg-slate-300 mx-1" />
            {[1, 2, 5].map((s) => (
              <button
                key={s}
                onClick={() => handleSpeed(s)}
                className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold transition ${
                  speed === s ? 'bg-white text-[#0F172A] shadow-xs font-bold' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Drill Runner Modal Trigger */}
          <button
            onClick={onOpenDemo}
            className="px-2.5 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-[#0F172A] border border-slate-300 text-xs font-medium flex items-center gap-1.5 transition shadow-xs"
          >
            <Award className="w-3.5 h-3.5 text-[#1B4332]" />
            <span className="hidden sm:inline">Drill Stepper</span>
          </button>

          {/* SOS Broadcast Button */}
          <button
            onClick={() => setSosModal(true)}
            className="px-2.5 py-1.5 rounded bg-red-700 hover:bg-red-800 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-xs"
          >
            <AlertOctagon className="w-3.5 h-3.5" />
            <span>Broadcast SOS</span>
          </button>

          {/* Operator Profile & Logout */}
          <div className="h-4 w-px bg-slate-300 mx-0.5 hidden sm:block" />
          <div className="flex items-center gap-2 pl-1">
            <div className="hidden sm:flex flex-col text-right">
              <span className="text-xs font-bold text-[#0F172A] leading-tight flex items-center gap-1 justify-end">
                <UserCircle className="w-3.5 h-3.5 text-slate-500" />
                {user?.username || 'Operator'}
              </span>
              <span className="text-[9px] font-mono font-semibold text-slate-500">
                {user?.role || 'RESPONDER'}
              </span>
            </div>
            <span
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold border uppercase ${
                user?.role === 'ADMIN'
                  ? 'bg-purple-50 text-purple-700 border-purple-200'
                  : user?.role === 'COORDINATOR'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-emerald-50 text-emerald-700 border-emerald-200'
              }`}
            >
              {user?.role || 'RESP'}
            </span>
            <button
              onClick={logout}
              title="Terminate Secure Session (Logout)"
              className="p-1.5 rounded hover:bg-red-50 text-slate-500 hover:text-red-700 border border-slate-200 transition"
              aria-label="Logout"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* SOS Modal Dialog */}
      {sosModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-300 rounded-lg max-w-md w-full p-5 shadow-lg space-y-4">
            <div className="flex items-center gap-2 text-red-700 border-b border-slate-200 pb-2">
              <ShieldAlert className="w-5 h-5 shrink-0" />
              <h3 className="font-bold text-sm text-[#0F172A]">Priority-0 Emergency SOS Broadcast</h3>
            </div>
            <p className="text-xs text-slate-600">
              This message preempts all background anti-entropy synchronization and floods across all active LoRa frequency channels.
            </p>
            <textarea
              value={sosText}
              onChange={(e) => setSosText(e.target.value)}
              rows={3}
              className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-xs text-[#0F172A] focus:outline-none focus:border-[#1B4332]"
              placeholder="Enter critical emergency broadcast message..."
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setSosModal(false)}
                className="px-3 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium border border-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleSendSOS}
                className="px-3.5 py-1.5 rounded bg-red-700 hover:bg-red-800 text-white text-xs font-bold transition shadow-xs"
              >
                Transmit SOS Packet
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
