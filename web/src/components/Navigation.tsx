import React from 'react';
import {
  LayoutDashboard,
  Mountain,
  Map,
  Share2,
  Building2,
  Activity,
  Database,
  Package,
  BarChart3,
  Flame,
  FileSpreadsheet,
  ShieldCheck,
  Radio,
  AlertOctagon,
} from 'lucide-react';

export type ViewType =
  | 'overview'
  | 'incidents'
  | 'terrain3d'
  | 'map2d'
  | 'topology'
  | 'stations'
  | 'comms'
  | 'events'
  | 'resources'
  | 'analytics'
  | 'scenarios'
  | 'reports';

interface NavigationProps {
  currentView: ViewType;
  onViewChange: (view: ViewType) => void;
  conflictsCount?: number;
  unreachableCount?: number;
}

export const Navigation: React.FC<NavigationProps> = ({
  currentView,
  onViewChange,
  conflictsCount = 0,
  unreachableCount = 0,
}) => {
  const tabs = [
    { id: 'overview', label: 'Operations Overview', icon: LayoutDashboard, hotkey: '1' },
    { id: 'incidents', label: 'Incidents & Dispatch', icon: AlertOctagon, hotkey: '0' },
    { id: 'terrain3d', label: '3D Mountain Twin', icon: Mountain, hotkey: '2' },
    { id: 'map2d', label: '2D Tactical Map', icon: Map, hotkey: '3' },
    {
      id: 'topology',
      label: 'Network Topology',
      icon: Share2,
      hotkey: '4',
      badge: unreachableCount > 0 ? `${unreachableCount} Cut` : undefined,
      badgeColor: 'bg-red-100 text-red-800 border border-red-200',
    },
    { id: 'stations', label: 'Station Fleet', icon: Building2, hotkey: '5' },
    { id: 'comms', label: 'Radio Comms Monitor', icon: Activity, hotkey: '6' },
    {
      id: 'events',
      label: 'Event Explorer & Ledger',
      icon: Database,
      hotkey: '7',
      badge: conflictsCount > 0 ? `${conflictsCount} Dispute` : undefined,
      badgeColor: 'bg-amber-100 text-amber-800 border border-amber-200',
    },
    { id: 'resources', label: 'Resources & Escrow', icon: Package, hotkey: '8' },
    { id: 'analytics', label: 'RF Telemetry & Metrics', icon: BarChart3, hotkey: '9' },
    { id: 'scenarios', label: 'Disaster Scenarios', icon: Flame },
    { id: 'reports', label: 'Audit & Invariant Proof', icon: FileSpreadsheet },
  ];

  return (
    <aside className="w-60 bg-white border-r border-slate-200 flex flex-col shrink-0 min-h-[calc(100vh-57px)]">
      {/* Section Label */}
      <div className="px-4 py-3 border-b border-slate-100">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
          Command Modules
        </span>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = currentView === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onViewChange(tab.id as ViewType)}
              className={`w-full flex items-center justify-between px-3 py-2 rounded text-xs transition select-none ${
                isActive
                  ? 'bg-[#1B4332] text-white font-semibold shadow-xs'
                  : 'text-slate-700 hover:text-slate-900 hover:bg-slate-100 font-medium'
              }`}
            >
              <div className="flex items-center gap-2.5 truncate">
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-emerald-300' : 'text-slate-500'}`} />
                <span className="truncate">{tab.label}</span>
              </div>

              <div className="flex items-center gap-1.5 shrink-0 ml-1">
                {tab.badge && (
                  <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${tab.badgeColor}`}>
                    {tab.badge}
                  </span>
                )}
                {tab.hotkey && (
                  <span
                    className={`text-[10px] font-mono px-1 py-0.2 rounded ${
                      isActive ? 'bg-[#143827] text-emerald-200' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {tab.hotkey}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </nav>

      {/* System Hardware Spec Footer */}
      <div className="p-3.5 border-t border-slate-200 bg-slate-50/70 text-[11px] text-slate-600 space-y-1">
        <div className="flex items-center gap-1.5 font-semibold text-slate-800">
          <Radio className="w-3.5 h-3.5 text-[#1B4332]" />
          <span>RF Physical Layer</span>
        </div>
        <p className="text-[10px] text-slate-500">
          Semtech SX1276 LoRa &bull; 865–867 MHz
        </p>
        <div className="flex items-center gap-1.5 text-[10px] text-emerald-800 font-medium pt-1">
          <ShieldCheck className="w-3 h-3 text-emerald-700" />
          <span>Ed25519 &bull; SQLite WAL</span>
        </div>
      </div>
    </aside>
  );
};
