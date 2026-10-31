"use client";

import React, { useState } from 'react';
import { TrendingUp, ArrowUpRight } from 'lucide-react';

interface DataPoint {
  label: string;
  velocity: number;
  forecast: number;
  date: string;
}

export const VelocityChartCard: React.FC<{ onExpandView?: () => void }> = ({ onExpandView }) => {
  const [period, setPeriod] = useState<'7D' | '14D' | '30D'>('7D');
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(4);

  const dataSets: Record<'7D' | '14D' | '30D', DataPoint[]> = {
    '7D': [
      { label: 'Mon', velocity: 45, forecast: 42, date: 'Oct 23' },
      { label: 'Tue', velocity: 68, forecast: 60, date: 'Oct 24' },
      { label: 'Wed', velocity: 74, forecast: 70, date: 'Oct 25' },
      { label: 'Thu', velocity: 82, forecast: 76, date: 'Oct 26' },
      { label: 'Fri', velocity: 94, forecast: 85, date: 'Oct 27' },
      { label: 'Sat', velocity: 52, forecast: 50, date: 'Oct 28' },
      { label: 'Sun', velocity: 65, forecast: 62, date: 'Oct 29' },
    ],
    '14D': [
      { label: 'W1 D1', velocity: 50, forecast: 48, date: 'Oct 16' },
      { label: 'W1 D3', velocity: 65, forecast: 60, date: 'Oct 18' },
      { label: 'W1 D5', velocity: 78, forecast: 72, date: 'Oct 20' },
      { label: 'W2 D1', velocity: 82, forecast: 78, date: 'Oct 23' },
      { label: 'W2 D3', velocity: 89, forecast: 82, date: 'Oct 25' },
      { label: 'W2 D5', velocity: 96, forecast: 88, date: 'Oct 27' },
      { label: 'W2 D7', velocity: 92, forecast: 85, date: 'Oct 29' },
    ],
    '30D': [
      { label: 'W1', velocity: 58, forecast: 55, date: 'Sprint 39' },
      { label: 'W2', velocity: 72, forecast: 68, date: 'Sprint 40' },
      { label: 'W3', velocity: 85, forecast: 80, date: 'Sprint 41' },
      { label: 'W4', velocity: 98, forecast: 88, date: 'Sprint 42' },
    ],
  };

  const points = dataSets[period] ?? dataSets['7D'];
  const maxVal = 110;
  const width = 460;
  const height = 180;
  const paddingX = 35;
  const paddingY = 25;

  const getCoordinates = (pts: DataPoint[], key: 'velocity' | 'forecast') => {
    const usableW = width - paddingX * 2;
    const usableH = height - paddingY * 2;
    return pts.map((p, idx) => {
      const x = paddingX + (idx / (pts.length - 1)) * usableW;
      const y = height - paddingY - (p[key] / maxVal) * usableH;
      return { x, y, data: p };
    });
  };

  const velocityCoords = getCoordinates(points, 'velocity');
  const forecastCoords = getCoordinates(points, 'forecast');

  // Generate smooth SVG cubic bezier path
  const createSmoothPath = (coords: { x: number; y: number }[]) => {
    if (coords.length === 0) return '';
    const first = coords[0];
    if (!first) return '';
    let d = `M ${first.x} ${first.y}`;
    for (let i = 0; i < coords.length - 1; i++) {
      const p0 = coords[i === 0 ? 0 : i - 1] ?? first;
      const p1 = coords[i] ?? first;
      const p2 = coords[i + 1] ?? p1;
      const p3 = coords[i + 2] ?? p2;

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
    }
    return d;
  };

  const velocityLine = createSmoothPath(velocityCoords);
  const forecastLine = createSmoothPath(forecastCoords);
  const fallbackCoord = { x: 0, y: 0, data: { label: '', velocity: 0, forecast: 0, date: '' } };
  const lastVelocity = velocityCoords[velocityCoords.length - 1] ?? fallbackCoord;
  const firstVelocity = velocityCoords[0] ?? fallbackCoord;
  const areaPath = `${velocityLine} L ${lastVelocity.x} ${height - paddingY} L ${firstVelocity.x} ${height - paddingY} Z`;

  const activePoint = (hoveredIndex !== null ? velocityCoords[hoveredIndex] : undefined) ?? lastVelocity;

  return (
    <div className="bento-card p-6 flex flex-col justify-between relative bg-white">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-stat uppercase tracking-wider text-[#6E6B68]">
              Velocity Telemetry
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-stat font-semibold text-[#449E74] bg-[#449E74]/10 px-2 py-0.5 rounded-full">
              <TrendingUp className="w-3 h-3" />
              +14.2% Delta
            </span>
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="font-stat text-3xl font-bold text-[#1E1E22] tracking-tight">
              {activePoint.data.velocity} <span className="text-sm font-normal text-[#6E6B68]">pts/day</span>
            </span>
            <span className="text-xs text-[#6E6B68]">
              Target: <span className="font-stat font-medium text-[#1E1E22]">{activePoint.data.forecast}</span>
            </span>
          </div>
        </div>

        {/* Period Switcher Pills & Expand */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-[#F3EFEA] p-1 rounded-full border border-[#E8E3DC]">
            {(['7D', '14D', '30D'] as const).map((p) => (
              <button
                key={p}
                onClick={() => {
                  setPeriod(p);
                  setHoveredIndex(null);
                }}
                className={`px-2.5 py-1 rounded-full text-[11px] font-stat font-medium transition-all ${
                  period === p
                    ? 'bg-[#1E1E22] text-white shadow-xs'
                    : 'text-[#6E6B68] hover:text-[#1E1E22]'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
          {onExpandView && (
            <button
              onClick={onExpandView}
              className="w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] flex items-center justify-center transition-colors shadow-xs"
              aria-label="Expand velocity analytics"
            >
              <ArrowUpRight className="w-4 h-4 text-[#1E1E22]" />
            </button>
          )}
        </div>
      </div>

      {/* Interactive SVG Chart Area */}
      <div className="relative w-full h-[190px] mt-2">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-full overflow-visible"
          preserveAspectRatio="none"
        >
          <defs>
            {/* Amber Gold to Transparent Gradient */}
            <linearGradient id="velocityWash" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#F4B33E" stopOpacity="0.35" />
              <stop offset="70%" stopColor="#FEEDB8" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#FAF8F5" stopOpacity="0.0" />
            </linearGradient>

            <linearGradient id="lineGlow" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#F4B33E" />
              <stop offset="100%" stopColor="#F06A42" />
            </linearGradient>
          </defs>

          {/* Horizontal Grid lines */}
          {[25, 50, 75, 100].map((val) => {
            const y = height - paddingY - (val / maxVal) * (height - paddingY * 2);
            return (
              <g key={val}>
                <line
                  x1={paddingX}
                  y1={y}
                  x2={width - paddingX}
                  y2={y}
                  stroke="#E8E3DC"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                  opacity="0.6"
                />
                <text
                  x={paddingX - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="font-stat fill-[#6E6B68] text-[9px]"
                >
                  {val}
                </text>
              </g>
            );
          })}

          {/* Area Fill */}
          <path d={areaPath} fill="url(#velocityWash)" />

          {/* Forecast Reference Line (Electric Iris / Slate dashed) */}
          <path
            d={forecastLine}
            fill="none"
            stroke="#5E5CE6"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            opacity="0.5"
          />

          {/* Main Velocity Curve */}
          <path
            d={velocityLine}
            fill="none"
            stroke="url(#lineGlow)"
            strokeWidth="3"
            strokeLinecap="round"
          />

          {/* Data Points and Dual-Ring Glowing Marker */}
          {velocityCoords.map((pt, idx) => {
            const isHovered = hoveredIndex === idx;
            return (
              <g
                key={idx}
                className="cursor-pointer"
                onMouseEnter={() => setHoveredIndex(idx)}
              >
                {/* Invisible larger hover zone */}
                <circle cx={pt.x} cy={pt.y} r="14" fill="transparent" />

                {isHovered ? (
                  // Dual-ring glowing marker specified in spec
                  <g>
                    <circle cx={pt.x} cy={pt.y} r="10" fill="#F4B33E" fillOpacity="0.25" />
                    <circle cx={pt.x} cy={pt.y} r="6" fill="#1E1E22" stroke="#F4B33E" strokeWidth="2.5" />
                    <circle cx={pt.x} cy={pt.y} r="2" fill="#FFFFFF" />
                  </g>
                ) : (
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="3.5"
                    fill="#FFFFFF"
                    stroke="#1E1E22"
                    strokeWidth="1.5"
                  />
                )}

                {/* X-axis labels */}
                <text
                  x={pt.x}
                  y={height - 6}
                  textAnchor="middle"
                  className={`font-stat text-[10px] transition-colors ${
                    isHovered ? 'fill-[#1E1E22] font-bold' : 'fill-[#6E6B68]'
                  }`}
                >
                  {pt.data.label}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Floating Tooltip Pin */}
        {activePoint && (
          <div
            className="absolute -top-3 pointer-events-none transition-all duration-200 -translate-x-1/2 bg-[#1E1E22] text-white px-2.5 py-1 rounded-xl shadow-md border border-white/10 text-center"
            style={{ left: `${(activePoint.x / width) * 100}%` }}
          >
            <div className="font-stat text-[11px] font-bold text-[#F4B33E]">
              {activePoint.data.velocity} pts
            </div>
            <div className="text-[9px] text-[#87858A]">
              {activePoint.data.date}
            </div>
          </div>
        )}
      </div>

      {/* Legend Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-[#E8E3DC]/60 text-[11px]">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#F4B33E]" />
            <span className="text-[#6E6B68] font-medium">Actual Output</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-[#5E5CE6] border-b border-dashed border-[#5E5CE6]" />
            <span className="text-[#6E6B68]">Forecast Target</span>
          </div>
        </div>
        <span className="font-stat text-[#449E74] font-medium">
          Sprint 42 on pace
        </span>
      </div>
    </div>
  );
};
