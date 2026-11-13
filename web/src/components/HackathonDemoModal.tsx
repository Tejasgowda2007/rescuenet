import React, { useState } from 'react';
import { Award, ArrowRight, CheckCircle2, RotateCcw, AlertTriangle, ShieldCheck, Play, Sparkles, X } from 'lucide-react';

interface HackathonDemoModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRefresh?: () => void;
}

export const HackathonDemoModal: React.FC<HackathonDemoModalProps> = ({
  isOpen,
  onClose,
  onRefresh,
}) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [stepData, setStepData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const stepsInfo = [
    { num: 1, title: 'Step 1: Baseline Network Operational', desc: '5 stations initialized with radio propagation and initial escrow pools.' },
    { num: 2, title: 'Step 2: Mountain Partition & Link Obstruction', desc: 'Trishul Ridge cuts line-of-sight. Charlie Mountain Shelter is isolated.' },
    { num: 3, title: 'Step 3: Offline Operations & Zero Lost Updates', desc: 'Conflicting doctor sightings logged. Bravo draws escrow. Charlie requests boat.' },
    { num: 4, title: 'Step 4: ECHO Elevated Relay Re-route', desc: 'Summit repeater at 2,350m online. 2-hop path discovered over ridge.' },
    { num: 5, title: 'Step 5: Multi-Hop Delta Synchronization', desc: 'Compact version vectors and deltas exchanged through ECHO relay.' },
    { num: 6, title: 'Step 6: Mathematical Invariant Verification', desc: 'Formal audit of convergence, zero lost updates, and boat exclusivity.' },
    { num: 7, title: 'Step 7: Human Triage Conflict Resolution', desc: 'Human medical lead resolves sighting; final consensus achieved.' },
  ];

  const runStep = async (stepNum: number) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/demo/step/${stepNum}`, { method: 'POST' });
      const data = await res.json();
      setStepData(data);
      setCurrentStep(stepNum);
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
      await fetch('/api/demo/reset', { method: 'POST' });
      setCurrentStep(1);
      setStepData(null);
      onRefresh?.();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
      <div className="bg-white border border-slate-300 rounded-lg max-w-2xl w-full p-5 shadow-xl space-y-4">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-[#1B4332] flex items-center justify-center text-white shadow-xs">
              <Award className="w-4 h-4 text-emerald-200" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#0F172A] flex items-center gap-2">
                <span>5-Minute Emergency Operations Demonstration Runner</span>
                <span className="text-[10px] font-mono font-bold bg-slate-100 text-slate-800 px-2 py-0.5 rounded border border-slate-300">
                  OFFICIAL DRILL
                </span>
              </h3>
              <p className="text-xs text-slate-500">
                Step-by-step interactive proof of offline survivability, relay re-routing, and zero lost updates.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1 rounded"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step Progress Buttons */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {stepsInfo.map((s) => (
            <button
              key={s.num}
              onClick={() => runStep(s.num)}
              className={`px-3 py-1 rounded text-xs font-bold transition whitespace-nowrap ${
                currentStep === s.num
                  ? 'bg-[#1B4332] text-white shadow-xs'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-200'
              }`}
            >
              Step {s.num}
            </button>
          ))}
        </div>

        {/* Current Step Description Card */}
        <div className="p-3.5 bg-slate-50 rounded border border-slate-200 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold text-[#0F172A]">
              {stepsInfo[currentStep - 1].title}
            </h4>
            <span className="text-[10px] text-slate-500 font-mono font-bold">
              PHASE {currentStep} OF 7
            </span>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            {stepsInfo[currentStep - 1].desc}
          </p>
        </div>

        {/* Live Step Execution Output */}
        {stepData && (
          <div className="space-y-2 text-xs">
            <div className="p-3 bg-emerald-50 border border-emerald-300 rounded space-y-1">
              <span className="font-bold text-emerald-950 uppercase tracking-wide text-[10px] block">
                Operational Outcome &bull; {stepData.action_summary}
              </span>
              <p className="text-emerald-900 font-semibold">{stepData.message}</p>
            </div>

            {stepData.logs && stepData.logs.length > 0 && (
              <div className="p-2.5 bg-slate-900 text-slate-200 font-mono text-[11px] rounded max-h-36 overflow-y-auto space-y-0.5">
                {stepData.logs.map((log: string, idx: number) => (
                  <div key={idx} className="leading-tight">&bull; {log}</div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Modal Footer Controls */}
        <div className="flex items-center justify-between pt-2 border-t border-slate-200">
          <button
            onClick={handleReset}
            className="px-3 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1.5 border border-slate-300 transition"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
            <span>Reset Demo State</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={() => runStep(currentStep)}
              disabled={loading}
              className="px-3.5 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300 text-xs font-bold transition flex items-center gap-1"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{loading ? 'Running...' : 'Re-Run Step'}</span>
            </button>

            {currentStep < 7 ? (
              <button
                onClick={() => runStep(currentStep + 1)}
                disabled={loading}
                className="px-4 py-1.5 rounded bg-[#1B4332] hover:bg-[#143827] text-white text-xs font-bold transition flex items-center gap-1 shadow-xs"
              >
                <span>Proceed to Step {currentStep + 1}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                onClick={onClose}
                className="px-4 py-1.5 rounded bg-emerald-800 hover:bg-emerald-900 text-white text-xs font-bold transition shadow-xs"
              >
                Complete Drill
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
