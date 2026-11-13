import React, { useState } from 'react';
import { TerrainData, StationData, LinkData } from '../../types';
import { Map, Radio, Compass, Navigation, Layers, Info } from 'lucide-react';

interface Map2DViewProps {
  terrain: TerrainData | null;
  stations: Record<string, StationData>;
  links: LinkData[];
  onSelectStation?: (id: string) => void;
}

export const Map2DView: React.FC<Map2DViewProps> = ({
  terrain,
  stations,
  links,
  onSelectStation,
}) => {
  const [showContours, setShowContours] = useState(true);
  const [showRiver, setShowRiver] = useState(true);
  const [showRoads, setShowRoads] = useState(true);
  const [showMargins, setShowMargins] = useState(true);

  // 50 km x 50 km mapped to SVG viewBox 0 0 1000 1000
  const mapX = (x_km: number) => (x_km / 50.0) * 1000.0;
  const mapY = (y_km: number) => (y_km / 50.0) * 1000.0;

  return (
    <div className="space-y-3">
      {/* Map Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-bold text-slate-800 uppercase tracking-wide text-[11px]">
            GIS Layers:
          </span>
          <button
            onClick={() => setShowContours(!showContours)}
            className={`px-2 py-0.5 rounded border text-[11px] font-medium transition ${
              showContours ? 'bg-[#1B4332] text-white border-[#1B4332]' : 'bg-white text-slate-600 border-slate-300'
            }`}
          >
            Terrain Contours
          </button>
          <button
            onClick={() => setShowRiver(!showRiver)}
            className={`px-2 py-0.5 rounded border text-[11px] font-medium transition ${
              showRiver ? 'bg-[#1B4332] text-white border-[#1B4332]' : 'bg-white text-slate-600 border-slate-300'
            }`}
          >
            Bhagirathi River
          </button>
          <button
            onClick={() => setShowRoads(!showRoads)}
            className={`px-2 py-0.5 rounded border text-[11px] font-medium transition ${
              showRoads ? 'bg-[#1B4332] text-white border-[#1B4332]' : 'bg-white text-slate-600 border-slate-300'
            }`}
          >
            Highway 10
          </button>
          <button
            onClick={() => setShowMargins(!showMargins)}
            className={`px-2 py-0.5 rounded border text-[11px] font-medium transition ${
              showMargins ? 'bg-[#1B4332] text-white border-[#1B4332]' : 'bg-white text-slate-600 border-slate-300'
            }`}
          >
            RF Link Margins
          </button>
        </div>

        <div className="text-[11px] text-slate-500 font-mono">
          UTM Grid: 50 km &times; 50 km &bull; 865–867 MHz LoRa
        </div>
      </div>

      {/* Main SVG Tactical GIS Canvas */}
      <div className="relative w-full aspect-square max-h-[620px] bg-[#EEF2F6] rounded border border-slate-300 overflow-hidden shadow-xs flex items-center justify-center">
        <svg viewBox="0 0 1000 1000" className="w-full h-full select-none font-sans">
          <defs>
            {/* GIS Metric Grid Pattern */}
            <pattern id="gisGrid" width="100" height="100" patternUnits="userSpaceOnUse">
              <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#CBD5E1" strokeWidth="0.75" />
            </pattern>
            {/* Subtle Sub-grid 20km */}
            <pattern id="gisSubGrid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#E2E8F0" strokeWidth="0.4" />
            </pattern>

            {/* Trishul Mountain Ridge Relief Shading */}
            <linearGradient id="ridgeShading" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#94A3B8" stopOpacity="0.4" />
              <stop offset="45%" stopColor="#64748B" stopOpacity="0.85" />
              <stop offset="55%" stopColor="#475569" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#94A3B8" stopOpacity="0.4" />
            </linearGradient>

            {/* Drop Shadow for Station Badges */}
            <filter id="badgeShadow" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="1" stdDeviation="1.5" floodColor="#0F172A" floodOpacity="0.15" />
            </filter>
          </defs>

          {/* Background Cartographic Surface */}
          <rect width="1000" height="1000" fill="#F4F6F8" />
          <rect width="1000" height="1000" fill="url(#gisSubGrid)" />
          <rect width="1000" height="1000" fill="url(#gisGrid)" />

          {/* Elevation Contour Lines */}
          {showContours && (
            <g opacity="0.6">
              {/* 500m contour */}
              <ellipse cx="260" cy="500" rx="180" ry="260" fill="none" stroke="#CBD5E1" strokeWidth="1" strokeDasharray="3,3" />
              <text x="180" y="500" fill="#94A3B8" fontSize="9" fontWeight="bold">500m</text>
              {/* 1000m contour */}
              <ellipse cx="500" cy="500" rx="220" ry="320" fill="none" stroke="#94A3B8" strokeWidth="1.2" />
              <text x="360" y="540" fill="#64748B" fontSize="9" fontWeight="bold">1000m</text>
              {/* 1800m contour */}
              <ellipse cx="620" cy="400" rx="140" ry="180" fill="none" stroke="#64748B" strokeWidth="1.4" />
              <text x="560" y="380" fill="#475569" fontSize="9" fontWeight="bold">1800m</text>
            </g>
          )}

          {/* Trishul Mountain Barrier Ridge (Major Terrain Obstacle) */}
          <g>
            <polygon
              points="200,1000 460,720 700,440 960,180 1000,230 760,510 520,790 260,1000"
              fill="url(#ridgeShading)"
            />
            {/* Ridge crest line */}
            <line x1="230" y1="1000" x2="980" y2="205" stroke="#334155" strokeWidth="2" strokeDasharray="6,3" />
            <text
              x="660"
              y="445"
              fill="#1E293B"
              fontSize="12"
              fontWeight="bold"
              transform="rotate(-40 660 445)"
              letterSpacing="2"
            >
              TRISHUL MOUNTAIN RIDGE (ELEV 2,420m) &bull; RF SHADOW ZONE
            </text>
          </g>

          {/* Bhagirathi River Gorge Path */}
          {showRiver && (
            <g>
              <path
                d="M 210,0 Q 240,240 300,500 T 360,800 T 400,1000"
                fill="none"
                stroke="#2563EB"
                strokeWidth="7"
                opacity="0.8"
                strokeLinecap="round"
              />
              <text x="225" y="220" fill="#1D4ED8" fontSize="10" fontWeight="bold">
                Bhagirathi River Gorge (320m)
              </text>
            </g>
          )}

          {/* Highway 10 Corridor */}
          {showRoads && (
            <g>
              <path
                d="M 160,0 L 210,164 L 280,400 L 440,700 L 520,1000"
                fill="none"
                stroke="#D97706"
                strokeWidth="3"
                strokeDasharray="8,4"
                opacity="0.75"
              />
              <text x="175" y="120" fill="#B45309" fontSize="9" fontWeight="bold">
                Highway 10
              </text>
            </g>
          )}

          {/* Radio Communication Links */}
          {links.map((link, idx) => {
            const s1 = stations[link.node_a];
            const s2 = stations[link.node_b];
            if (!s1 || !s2) return null;

            const x1 = mapX(s1.coords[0]);
            const y1 = mapY(s1.coords[1]);
            const x2 = mapX(s2.coords[0]);
            const y2 = mapY(s2.coords[1]);

            let strokeColor = '#166534'; // Viable LoRa link (Forest Green)
            let strokeWidth = '2.5';
            let strokeDash = 'none';

            if (link.status === 'DEGRADED') {
              strokeColor = '#B45309'; // Muted amber
              strokeWidth = '2';
            } else if (link.status === 'BLOCKED' || link.status === 'CUT' || link.is_manually_cut) {
              strokeColor = '#DC2626'; // Restrained red
              strokeWidth = '2';
              strokeDash = '7,5';
            }

            const midX = (x1 + x2) / 2;
            const midY = (y1 + y2) / 2;

            return (
              <g key={`map-link-${idx}`}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={strokeColor}
                  strokeWidth={strokeWidth}
                  strokeDasharray={strokeDash}
                  opacity={link.is_connected ? 0.9 : 0.6}
                />
                {/* Margin Badge along link */}
                {showMargins && (
                  <g transform={`translate(${midX}, ${midY})`}>
                    <rect
                      x="-22"
                      y="-8"
                      width="44"
                      height="16"
                      rx="2"
                      fill="#FFFFFF"
                      stroke={strokeColor}
                      strokeWidth="1"
                    />
                    <text
                      x="0"
                      y="3"
                      textAnchor="middle"
                      fill={strokeColor}
                      fontSize="9"
                      fontFamily="monospace"
                      fontWeight="bold"
                    >
                      {link.is_connected ? `${link.margin_db > 0 ? '+' : ''}${link.margin_db}dB` : 'CUT'}
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          {/* Station Markers with GIS Symbology */}
          {Object.values(stations).map((stn) => {
            const cx = mapX(stn.coords[0]);
            const cy = mapY(stn.coords[1]);
            const isOnline = stn.status === 'ONLINE';
            const isDegraded = stn.status === 'DEGRADED';
            const statusColor = isOnline ? '#166534' : isDegraded ? '#D97706' : '#DC2626';
            const isPhysical = stn.id === 'alpha';

            return (
              <g
                key={`map-stn-${stn.id}`}
                className="cursor-pointer"
                onClick={() => onSelectStation?.(stn.id)}
              >
                {/* Outer GIS Ring */}
                <circle cx={cx} cy={cy} r="14" fill="#FFFFFF" stroke={statusColor} strokeWidth="2.5" />
                <circle cx={cx} cy={cy} r="6" fill={statusColor} />

                {/* Information Card Badge */}
                <g transform={`translate(${cx - 70}, ${cy + 18})`} filter="url(#badgeShadow)">
                  <rect
                    width="140"
                    height="38"
                    rx="3"
                    fill="#FFFFFF"
                    stroke="#CBD5E1"
                    strokeWidth="1"
                  />
                  {/* Top line: Name & Role */}
                  <text x="6" y="14" fill="#0F172A" fontSize="10.5" fontWeight="bold">
                    {stn.name.split(' ')[0]} ({stn.id.toUpperCase()})
                  </text>
                  <text x="134" y="14" textAnchor="end" fill="#64748B" fontSize="9" fontWeight="bold" fontFamily="monospace">
                    {isPhysical ? 'PHYS' : 'SIM'}
                  </text>
                  {/* Bottom line: Elevation & Battery */}
                  <text x="6" y="29" fill="#475569" fontSize="9" fontFamily="monospace">
                    Elev: {stn.elevation_m}m &bull; Bat: {stn.battery_pct}%
                  </text>
                </g>
              </g>
            );
          })}

          {/* GIS Coordinate Grid Labels */}
          <g fill="#64748B" fontSize="10" fontFamily="monospace" fontWeight="600">
            {/* Top axis */}
            <text x="10" y="18">0 km</text>
            <text x="200" y="18">10 km</text>
            <text x="400" y="18">20 km</text>
            <text x="600" y="18">30 km</text>
            <text x="800" y="18">40 km</text>
            <text x="965" y="18">50 km</text>
            {/* Left axis */}
            <text x="8" y="205">10 km</text>
            <text x="8" y="405">20 km</text>
            <text x="8" y="605">30 km</text>
            <text x="8" y="805">40 km</text>
            <text x="8" y="990">50 km</text>
          </g>

          {/* Compass Rose in Upper Right */}
          <g transform="translate(945, 55)">
            <circle cx="0" cy="0" r="22" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="1" />
            <polygon points="0,-18 5,-4 0,0 -5,-4" fill="#1B4332" />
            <polygon points="0,18 5,4 0,0 -5,4" fill="#94A3B8" />
            <text x="0" y="-22" textAnchor="middle" fill="#0F172A" fontSize="10" fontWeight="bold">N</text>
          </g>

          {/* Scale Bar in Lower Left */}
          <g transform="translate(45, 960)">
            <rect x="0" y="0" width="200" height="6" fill="#0F172A" />
            <rect x="0" y="0" width="100" height="6" fill="#FFFFFF" stroke="#0F172A" strokeWidth="1" />
            <text x="0" y="18" fill="#0F172A" fontSize="9" fontFamily="monospace">0 km</text>
            <text x="100" y="18" textAnchor="middle" fill="#0F172A" fontSize="9" fontFamily="monospace">5 km</text>
            <text x="200" y="18" textAnchor="end" fill="#0F172A" fontSize="9" fontFamily="monospace">10 km</text>
          </g>
        </svg>
      </div>
    </div>
  );
};
