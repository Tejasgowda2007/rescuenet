import React, { useEffect, useState } from 'react';
import { ScenarioPreset } from '../../types';
import { Flame, CloudRain, AlertTriangle, ShieldCheck, Play, RotateCcw } from 'lucide-react';

interface ScenariosViewProps {
  onRefresh?: () => void;
}

export const ScenariosView: React.FC<ScenariosViewProps> = ({ onRefresh }) => {
  const [scenarios, setScenarios] = useState<ScenarioPreset[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/scenarios')
      .then((r) => r.json())
      .then((d) => setScenarios(d))
      .catch(() => {});
  }, []);

  const handleApply = async (id: string) => {
    setLoading(true);
    try {
      const res = await fetch('/api/scenarios/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: id }),
      });
      const data = await res.json();
      setActiveId(id);
      setMessage(data.logs?.[0] || 'Disaster scenario applied to live simulation topology.');
      setTimeout(() => setMessage(null), 5000);
      onRefresh?.();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    try {
      await fetch('/api/scenarios/reset', { method: 'POST' });
      setActiveId(null);
      setMessage('Network links restored to 100% connected baseline.');
      setTimeout(() => setMessage(null), 4000);
      onRefresh?.();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
            <Flame className="w-4 h-4 text-[#1B4332]" />
            <span>Disaster Scenario Laboratory &amp; Failure Injection</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Trigger terrain-based radio link obstructions, severe weather attenuation, and independent offline operations.
          </p>
        </div>

        <button
          onClick={handleReset}
          className="px-3 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold flex items-center gap-1.5 border border-slate-300 transition shadow-xs"
        >
          <RotateCcw className="w-3.5 h-3.5 text-[#1B4332]" />
          <span>Reset All to Clean Baseline</span>
        </button>
      </div>

      {message && (
        <div className="p-3 bg-emerald-50 border border-emerald-300 rounded text-xs text-emerald-900 font-medium">
          {message}
        </div>
      )}

      {/* Grid of 8 Disaster Scenarios */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {scenarios.map((sc) => {
          const isSelected = activeId === sc.id;
          const isCritical = sc.severity === 'CRITICAL';

          return (
            <div
              key={sc.id}
              className={`p-3.5 rounded border transition ${
                isSelected
                  ? 'bg-slate-50 border-[#1B4332] shadow-sm'
                  : 'bg-white border-slate-200 hover:bg-slate-50/70'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div>
                  <h4 className="text-xs font-bold text-slate-900">{sc.name}</h4>
                  <span className="text-[10px] text-slate-500 font-mono">
                    Hazard: {sc.hazard_type.toUpperCase()}
                  </span>
                </div>

                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                    isCritical
                      ? 'bg-red-50 text-red-800 border border-red-200'
                      : 'bg-amber-50 text-amber-800 border border-amber-200'
                  }`}
                >
                  {sc.severity}
                </span>
              </div>

              <p className="text-xs text-slate-600 mb-2.5 leading-relaxed">{sc.description}</p>

              <div className="flex flex-wrap items-center justify-between text-[11px] border-t border-slate-100 pt-2 gap-2">
                <div className="text-slate-500 space-x-2">
                  <span>Rain: <strong className="text-slate-800">{sc.rain_mm_h} mm/h</strong></span>
                  <span>Cut Links: <strong className="text-red-700">{sc.cut_links?.length ?? 0}</strong></span>
                </div>

                <button
                  onClick={() => handleApply(sc.id)}
                  disabled={loading && isSelected}
                  className={`px-2.5 py-1 rounded text-xs font-semibold flex items-center gap-1 transition ${
                    isSelected
                      ? 'bg-[#1B4332] text-white'
                      : 'bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300'
                  }`}
                >
                  <Play className="w-3 h-3" />
                  <span>{isSelected ? 'Scenario Active' : 'Inject Scenario'}</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
