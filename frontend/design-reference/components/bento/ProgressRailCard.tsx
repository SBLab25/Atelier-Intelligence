import React from 'react';
import { ArrowUpRight, Layers } from 'lucide-react';
import { computeAllocationPercentages } from '../../utils/bentoMetrics';

interface ProgressRailCardProps {
  onExpandView?: () => void;
}

export const ProgressRailCard: React.FC<ProgressRailCardProps> = ({ onExpandView }) => {
  const segments = [
    { label: 'Interviews & Recruiting', count: 14, color: '#1E1E22' },
    { label: 'Client Architecture', count: 32, color: '#F4B33E' },
    { label: 'Design System Polish', count: 20, color: '#F06A42' },
    { label: 'Internal R&D / Sandbox', count: 10, color: '#C8C5CB', stripe: true },
  ];

  const calculated = computeAllocationPercentages(segments);
  const totalItems = segments.reduce((acc, s) => acc + s.count, 0);

  return (
    <div className="bento-card p-6 flex flex-col justify-between bg-white relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-[11px] font-stat uppercase tracking-wider text-[#6E6B68] block">
            Resource Allocation
          </span>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-[#1E1E22] tracking-tight">
              Horizontal Progress Rail
            </h3>
            <span className="font-stat text-xs bg-[#F3EFEA] text-[#1E1E22] px-2 py-0.5 rounded-full font-medium">
              {totalItems} total allocations
            </span>
          </div>
        </div>
        {onExpandView && (
          <button
            onClick={onExpandView}
            className="w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] flex items-center justify-center transition-colors shadow-xs"
            aria-label="Expand progress rail details"
          >
            <ArrowUpRight className="w-4 h-4 text-[#1E1E22]" />
          </button>
        )}
      </div>

      {/* The Multi-Segment Striped Progress Rail */}
      <div className="my-auto py-2">
        <div className="w-full h-8 rounded-full bg-[#F3EFEA] p-1 flex items-center gap-1 shadow-inner overflow-hidden border border-[#E8E3DC]">
          {calculated.map((seg, idx) => (
            <div
              key={idx}
              style={{ width: `${seg.percentage}%` }}
              title={`${seg.label}: ${seg.percentage}% (${seg.count} items)`}
              className={`h-full rounded-full transition-all duration-500 relative group cursor-pointer ${
                seg.stripe ? 'bg-[#DCD8D2]' : ''
              }`}
            >
              <div
                className="w-full h-full rounded-full"
                style={{
                  backgroundColor: seg.stripe ? undefined : seg.color,
                  backgroundImage: seg.stripe
                    ? 'repeating-linear-gradient(45deg, #A8A5AB 0, #A8A5AB 4px, #DCD8D2 4px, #DCD8D2 8px)'
                    : undefined,
                }}
              />
              {/* Tooltip on hover */}
              <div className="absolute -top-8 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none bg-[#1E1E22] text-white text-[10px] font-stat px-2 py-0.5 rounded-md whitespace-nowrap z-20">
                {seg.percentage}% · {seg.count} items
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Legend & Stats Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-[#E8E3DC]/60 text-xs">
        {calculated.map((seg, idx) => (
          <div key={idx} className="flex items-start gap-2">
            <span
              className="w-3 h-3 rounded-full mt-0.5 shrink-0"
              style={{
                backgroundColor: seg.stripe ? undefined : seg.color,
                backgroundImage: seg.stripe
                  ? 'repeating-linear-gradient(45deg, #6E6B68 0, #6E6B68 2px, #E8E3DC 2px, #E8E3DC 4px)'
                  : undefined,
              }}
            />
            <div className="min-w-0">
              <span className="text-[11px] font-medium text-[#1E1E22] block truncate">
                {seg.label}
              </span>
              <span className="text-[10px] font-stat text-[#6E6B68]">
                {seg.percentage}% ({seg.count})
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
