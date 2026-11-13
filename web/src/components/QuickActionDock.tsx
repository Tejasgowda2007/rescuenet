import React, { useState } from 'react';
import {
  Zap,
  Scissors,
  Check,
  RefreshCw,
  Award,
  AlertOctagon,
  Mountain,
  TowerControl,
  Radio,
  Send,
  X,
} from 'lucide-react';

interface QuickActionDockProps {
  onOpenDemo: () => void;
  onRefreshAll: () => void;
  onTriggerSOS: (msg: string) => void;
}

export const QuickActionDock: React.FC<QuickActionDockProps> = ({
  onOpenDemo,
  onRefreshAll,
  onTriggerSOS,
}) => {
  const [sosModalOpen, setSosModalOpen] = useState(false);
  const [sosText, setSosText] = useState('Critical Mudslide Survivor Detected in Sector Charlie');
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const showFeedback = (msg: string) => {
    setActionFeedback(msg);
    setTimeout(() => setActionFeedback(null), 3500);
  };

  const handleCutTrishulPass = async () => {
    await fetch('/api/links/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_a: 'alpha', node_b: 'charlie' }),
    });
    showFeedback('Trishul Ridge direct pass severed. Network partitioned.');
    onRefreshAll();
  };

  const handleToggleEchoRelay = async () => {
    try {
      const res = await fetch('/api/stations/echo');
      const data = await res.json();
      const currentStatus = data.detail?.status;
      const nextStatus = currentStatus === 'ONLINE' ? 'DESTROYED' : 'ONLINE';
      await fetch('/api/stations/echo/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus }),
      });
      showFeedback(`ECHO Ridge Summit Relay is now ${nextStatus}`);
      onRefreshAll();
    } catch (e) {
      console.error(e);
    }
  };

  const handleSyncMesh = async () => {
    try {
      await fetch('/api/actions/sync?source_id=alpha', { method: 'POST' });
      showFeedback('Pairwise anti-entropy sync executed across viable links.');
      onRefreshAll();
    } catch (e) {
      console.error(e);
    }
  };

  const handleSendSOS = () => {
    onTriggerSOS(sosText);
    setSosModalOpen(false);
    showFeedback('Priority-0 SOS transmitted across LoRa frequencies.');
  };

  return (
    <>
      {/* Action Feedback Notification */}
      {actionFeedback && (
        <div className="fixed bottom-16 left-1/2 -translate-x-1/2 z-50 bg-[#0F172A] text-white px-4 py-2 rounded shadow-md text-xs font-semibold flex items-center gap-2 border border-slate-700">
          <Zap className="w-3.5 h-3.5 text-amber-400" />
          <span>{actionFeedback}</span>
        </div>
      )}

      {/* Industrial Emergency Operations Command Bar */}
      <footer className="fixed bottom-0 left-0 right-0 z-30 bg-white border-t border-slate-200 px-4 py-2 shadow-xs flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Emergency Command Actions:
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Action 1: SOS Broadcast */}
          <button
            onClick={() => setSosModalOpen(true)}
            className="px-2.5 py-1 rounded bg-red-700 hover:bg-red-800 text-white font-bold text-xs flex items-center gap-1.5 transition shadow-xs"
          >
            <AlertOctagon className="w-3.5 h-3.5" />
            <span>Transmit SOS</span>
          </button>

          {/* Action 2: Sever Trishul Pass */}
          <button
            onClick={handleCutTrishulPass}
            className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300 font-semibold text-xs flex items-center gap-1.5 transition"
          >
            <Scissors className="w-3.5 h-3.5 text-red-600" />
            <span>Sever Trishul Pass</span>
          </button>

          {/* Action 3: Toggle Echo Relay */}
          <button
            onClick={handleToggleEchoRelay}
            className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300 font-semibold text-xs flex items-center gap-1.5 transition"
          >
            <TowerControl className="w-3.5 h-3.5 text-[#1B4332]" />
            <span>Toggle Echo Relay</span>
          </button>

          {/* Action 4: Pairwise Sync */}
          <button
            onClick={handleSyncMesh}
            className="px-2.5 py-1 rounded bg-emerald-800 hover:bg-emerald-900 text-white font-semibold text-xs flex items-center gap-1.5 transition shadow-xs"
          >
            <RefreshCw className="w-3.5 h-3.5 text-emerald-200" />
            <span>Sync Anti-Entropy</span>
          </button>

          {/* Action 5: 5-Minute Drill Runner */}
          <button
            onClick={onOpenDemo}
            className="px-2.5 py-1 rounded bg-[#0F172A] hover:bg-slate-800 text-white font-semibold text-xs flex items-center gap-1.5 transition shadow-xs"
          >
            <Award className="w-3.5 h-3.5 text-amber-400" />
            <span>5-Min Drill Runner</span>
          </button>
        </div>
      </footer>

      {/* SOS Modal Dialog */}
      {sosModalOpen && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-300 rounded-lg max-w-md w-full p-5 shadow-lg space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="flex items-center gap-2 text-red-700">
                <AlertOctagon className="w-5 h-5" />
                <h3 className="font-bold text-sm text-[#0F172A]">Transmit Priority-0 Emergency SOS</h3>
              </div>
              <button
                onClick={() => setSosModalOpen(false)}
                className="p-1 rounded text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <textarea
              value={sosText}
              onChange={(e) => setSosText(e.target.value)}
              rows={3}
              className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-xs text-slate-900 focus:outline-none focus:border-[#1B4332]"
              placeholder="Enter critical survivor/incident location and instructions..."
            />

            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setSosModalOpen(false)}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-700 rounded text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleSendSOS}
                className="px-3.5 py-1.5 bg-red-700 hover:bg-red-800 text-white rounded text-xs font-bold transition shadow-xs"
              >
                Transmit SOS over Air
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
