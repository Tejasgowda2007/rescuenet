import React, { useState } from 'react';
import { StationData, LinkData } from '../../types';
import { Share2, Route, Scissors, Check, AlertOctagon, ArrowRight, ShieldCheck, Zap, Radio, Info } from 'lucide-react';

interface TopologyViewProps {
  stations: Record<string, StationData>;
  links: LinkData[];
  onToggleLink: (n1: string, n2: string) => void;
  onHealAll: () => void;
}

export const TopologyView: React.FC<TopologyViewProps> = ({
  stations,
  links,
  onToggleLink,
  onHealAll,
}) => {
  const [source, setSource] = useState('alpha');
  const [dest, setDest] = useState('charlie');
  const [routeResult, setRouteResult] = useState<string[] | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [hoveredLink, setHoveredLink] = useState<LinkData | null>(null);

  const calculateRoute = () => {
    setCalcLoading(true);
    fetch('/api/topology')
      .then((r) => r.json())
      .then((data) => {
        const routes = data.routes?.[source];
        const path = routes?.[dest];
        setRouteResult(path);
        setCalcLoading(false);
      })
      .catch(() => setCalcLoading(false));
  };

  // Convert (x_km, y_km) to SVG coordinates inside 800 x 420 viewBox
  const toSvgCoords = (x_km: number, y_km: number) => {
    const sx = (x_km / 50.0) * 680.0 + 60.0;
    const sy = ((50.0 - y_km) / 50.0) * 320.0 + 50.0;
    return { x: sx, y: sy };
  };

  // Check if a link is part of the currently displayed route
  const isLinkInRoute = (nodeA: string, nodeB: string) => {
    if (!routeResult || routeResult.length < 2) return false;
    for (let i = 0; i < routeResult.length - 1; i++) {
      const u = routeResult[i];
      const v = routeResult[i + 1];
      if ((u === nodeA && v === nodeB) || (u === nodeB && v === nodeA)) {
        return true;
      }
    }
    return false;
  };

  return (
    <div className="space-y-4">
      {/* Header and Operational Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
            <Share2 className="w-4 h-4 text-[#1B4332]" />
            <span>Radio Mesh Topology Graph &amp; Multi-Hop Routing</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            NetworkX graph edges evaluated from Line-of-Sight terrain diffraction and knife-edge attenuation.
          </p>
        </div>

        <button
          onClick={onHealAll}
          className="px-3 py-1.5 rounded bg-emerald-800 hover:bg-emerald-900 text-white font-semibold text-xs flex items-center gap-1.5 transition shadow-xs"
        >
          <Check className="w-3.5 h-3.5" />
          <span>Restore All Radio Links</span>
        </button>
      </div>

      {/* Main Graph Card */}
      <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between border-b border-slate-100 pb-2.5 gap-2">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#1B4332]" />
            <span className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
              Interactive Topology (Click any link to sever or restore)
            </span>
          </div>

          <div className="flex items-center gap-4 text-[11px] text-slate-600 font-medium">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-700" />
              <span>Healthy Link</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-600" />
              <span>Marginal (0–10 dB)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 border-t border-dashed border-red-600" />
              <span>Severed / Blocked</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-1 bg-[#0F172A] rounded" />
              <span>Active Route</span>
            </div>
          </div>
        </div>

        {/* SVG Mesh Canvas */}
        <div className="relative w-full h-[380px] bg-[#F8FAFC] rounded border border-slate-200 overflow-hidden flex items-center justify-center">
          <svg viewBox="0 0 800 420" className="w-full h-full select-none font-sans">
            <defs>
              <pattern id="topoGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#E2E8F0" strokeWidth="0.75" />
              </pattern>
            </defs>
            <rect width="800" height="420" fill="#F8FAFC" />
            <rect width="800" height="420" fill="url(#topoGrid)" />

            {/* Trishul Mountain Ridge Relief in Background */}
            <polygon
              points="240,420 380,290 520,170 700,60 740,90 560,200 420,320 280,420"
              fill="#E2E8F0"
              opacity="0.75"
            />
            <text
              x="440"
              y="240"
              fill="#94A3B8"
              fontSize="11"
              fontWeight="bold"
              transform="rotate(-32 440 240)"
              letterSpacing="1"
            >
              TRISHUL MOUNTAIN RIDGE (BARRIER)
            </text>

            {/* Radio Link Lines */}
            {links.map((link, idx) => {
              const s1 = stations[link.node_a];
              const s2 = stations[link.node_b];
              if (!s1 || !s2) return null;

              const p1 = toSvgCoords(s1.coords[0], s1.coords[1]);
              const p2 = toSvgCoords(s2.coords[0], s2.coords[1]);
              const inRoute = isLinkInRoute(link.node_a, link.node_b);

              let stroke = '#166534'; // Forest Green
              if (link.status === 'DEGRADED') stroke = '#B45309';
              if (link.status === 'BLOCKED' || link.status === 'CUT' || link.is_manually_cut) stroke = '#DC2626';

              if (inRoute) {
                stroke = '#0F172A'; // Navy active route
              }

              const isDashed = !link.is_connected || link.is_manually_cut || link.status === 'BLOCKED';

              return (
                <g
                  key={idx}
                  onClick={() => onToggleLink(link.node_a, link.node_b)}
                  onMouseEnter={() => setHoveredLink(link)}
                  onMouseLeave={() => setHoveredLink(null)}
                  className="cursor-pointer group"
                >
                  {/* Invisible thicker hit line for easy clicking */}
                  <line
                    x1={p1.x}
                    y1={p1.y}
                    x2={p2.x}
                    y2={p2.y}
                    stroke="transparent"
                    strokeWidth="18"
                  />
                  {/* Visible Link Line */}
                  <line
                    x1={p1.x}
                    y1={p1.y}
                    x2={p2.x}
                    y2={p2.y}
                    stroke={stroke}
                    strokeWidth={inRoute ? 3.5 : isDashed ? 1.8 : 2.4}
                    strokeDasharray={isDashed ? '6,5' : 'none'}
                    className="transition-all duration-200"
                  />
                  {/* Midpoint Margin Badge */}
                  <g transform={`translate(${(p1.x + p2.x) / 2}, ${(p1.y + p2.y) / 2})`}>
                    <rect
                      x="-22"
                      y="-9"
                      width="44"
                      height="18"
                      rx="2"
                      fill="#FFFFFF"
                      stroke={stroke}
                      strokeWidth="1"
                    />
                    <text
                      x="0"
                      y="4"
                      textAnchor="middle"
                      fill={stroke}
                      fontSize="9"
                      fontWeight="bold"
                      fontFamily="monospace"
                    >
                      {link.margin_db > -50 ? `${link.margin_db}dB` : 'CUT'}
                    </text>
                  </g>
                </g>
              );
            })}

            {/* Station Nodes */}
            {Object.values(stations).map((stn) => {
              const pos = toSvgCoords(stn.coords[0], stn.coords[1]);
              const isSource = source === stn.id;
              const isDest = dest === stn.id;
              const inRoute = routeResult?.includes(stn.id);

              let nodeColor = '#166534';
              if (stn.status === 'DEGRADED') nodeColor = '#D97706';
              if (stn.status === 'POWER_DEPLETED' || stn.status === 'DESTROYED') nodeColor = '#DC2626';

              return (
                <g key={stn.id} transform={`translate(${pos.x}, ${pos.y})`} className="cursor-pointer">
                  {/* Active Route Highlight Box */}
                  {inRoute && (
                    <rect
                      x="-22"
                      y="-22"
                      width="44"
                      height="44"
                      rx="6"
                      fill="none"
                      stroke="#0F172A"
                      strokeWidth="2"
                      strokeDasharray="4,2"
                    />
                  )}

                  {/* Node Base Badge */}
                  <circle
                    r="15"
                    fill="#FFFFFF"
                    stroke={isSource ? '#1D4ED8' : isDest ? '#DC2626' : nodeColor}
                    strokeWidth="3"
                  />
                  <circle r="6" fill={nodeColor} />

                  {/* Node Name & Meta */}
                  <text
                    x="0"
                    y="-20"
                    textAnchor="middle"
                    fill="#0F172A"
                    fontSize="11"
                    fontWeight="bold"
                  >
                    {stn.name.split(' ')[0]}
                  </text>
                  <text
                    x="0"
                    y="28"
                    textAnchor="middle"
                    fill="#64748B"
                    fontSize="9.5"
                    fontWeight="600"
                    fontFamily="monospace"
                  >
                    {stn.elevation_m}m &bull; {stn.id.toUpperCase()}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Hovered Link Info Tooltip */}
          {hoveredLink && (
            <div className="absolute top-3 left-3 bg-white px-3 py-2 rounded border border-slate-300 text-xs shadow-md pointer-events-none">
              <span className="font-bold text-[#0F172A] block">
                {stations[hoveredLink.node_a]?.name.split(' ')[0]} &harr; {stations[hoveredLink.node_b]?.name.split(' ')[0]}
              </span>
              <span className="text-slate-600 text-[11px] block mt-0.5">
                Distance: <strong className="text-slate-900">{hoveredLink.distance_km} km</strong> &bull; Margin:{' '}
                <strong className={hoveredLink.margin_db >= 10 ? 'text-emerald-700' : 'text-amber-700'}>
                  {hoveredLink.margin_db} dB
                </strong>{' '}
                &bull; PER: <strong>{(hoveredLink.per * 100).toFixed(1)}%</strong>
              </span>
              <span className="text-[10px] text-[#1B4332] font-semibold block mt-0.5">
                Click link to {hoveredLink.is_connected ? 'sever / cut' : 'restore'} &rarr;
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Multi-Hop Dijkstra Path Calculator */}
      <div className="bg-white border border-slate-200 rounded p-4 shadow-xs space-y-3">
        <div className="flex items-center gap-2">
          <Route className="w-4 h-4 text-[#1B4332]" />
          <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
            Cost-Aware Dijkstra Multi-Hop Route Finder
          </h4>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Source Station</label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-xs text-slate-900 font-medium"
            >
              {Object.values(stations).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.id.toUpperCase()}) &bull; {s.elevation_m}m
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Destination Station</label>
            <select
              value={dest}
              onChange={(e) => setDest(e.target.value)}
              className="w-full bg-slate-50 border border-slate-300 rounded p-2 text-xs text-slate-900 font-medium"
            >
              {Object.values(stations).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.id.toUpperCase()}) &bull; {s.elevation_m}m
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={calculateRoute}
            disabled={source === dest}
            className="w-full py-2 px-3 rounded bg-[#1B4332] hover:bg-[#143827] disabled:bg-slate-200 text-white font-bold text-xs shadow-xs transition"
          >
            {calcLoading ? 'Computing Shortest Path...' : 'Find Lowest-Cost Route'}
          </button>
        </div>

        {routeResult !== null && (
          <div className="mt-2 p-3 bg-slate-50 rounded border border-slate-200 text-xs">
            {routeResult ? (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 font-bold text-emerald-900">
                  <Check className="w-4 h-4 text-emerald-700" />
                  <span>Optimal Route Identified ({routeResult.length - 1} Hops):</span>
                </div>
                <div className="flex items-center gap-2 font-mono font-bold text-slate-900 overflow-x-auto py-1">
                  {routeResult.map((node, i) => (
                    <React.Fragment key={node}>
                      <span className="px-2.5 py-1 rounded bg-white border border-slate-300 text-xs">
                        {stations[node]?.name.split(' ')[0] || node} ({node.toUpperCase()})
                      </span>
                      {i < routeResult.length - 1 && (
                        <ArrowRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-red-700 font-semibold">
                <AlertOctagon className="w-4 h-4 shrink-0" />
                <span>No viable radio path exists. Mountain terrain or severed links isolate these sectors!</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
