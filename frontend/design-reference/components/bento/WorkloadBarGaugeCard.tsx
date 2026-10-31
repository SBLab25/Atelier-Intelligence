import React, { useState } from 'react';
import { Clock, ArrowUpRight } from 'lucide-react';
import { DailyWorkload } from '../../types';

interface WorkloadBarGaugeCardProps {
  workloadDays: DailyWorkload[];
  onExpandView?: () => void;
}

export const WorkloadBarGaugeCard: React.FC<WorkloadBarGaugeCardProps> = ({
  workloadDays,
  onExpandView,
}) => {
  const [selectedDay, setSelectedDay] = useState<string>('Wed');

  const maxMinutes = 420; // 7 hours max scale

  return (
    <div className="bento-card p-6 flex flex-col justify-between bg-white relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-[11px] font-stat uppercase tracking-wider text-[#6E6B68] block">
            Workload Distribution
          </span>
          <h3 className="text-base font-semibold text-[#1E1E22] tracking-tight">
            Daily Workload Heatmap
          </h3>
        </div>
        {onExpandView && (
          <button
            onClick={onExpandView}
            className="w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] flex items-center justify-center transition-colors shadow-xs"
            aria-label="Expand workload details"
          >
            <ArrowUpRight className="w-4 h-4 text-[#1E1E22]" />
          </button>
        )}
      </div>

      {/* Bar Gauges Container */}
      <div className="pt-6 pb-2">
        <div className="h-44 flex items-end justify-between gap-2 px-1 relative">
          {workloadDays.map((d) => {
            const heightPercent = Math.min(100, (d.totalMinutes / maxMinutes) * 100);
            const isSelected = selectedDay === d.day;
            const isPeak = d.isPeak;

            return (
              <div
                key={d.day}
                onClick={() => setSelectedDay(d.day)}
                className="flex-1 flex flex-col items-center h-full justify-end group cursor-pointer relative"
              >
                {/* Active Pill Callout: especially on peak or selected day (e.g. "5h 23m") */}
                {(isPeak || isSelected) && (
                  <div
                    className={`absolute -top-7 z-20 px-2 py-0.5 rounded-full text-[10px] font-stat font-semibold tracking-tight shadow-sm whitespace-nowrap transition-all duration-200 ${
                      isPeak
                        ? 'bg-[#1E1E22] text-[#F4B33E] ring-1 ring-[#F4B33E]/40'
                        : 'bg-[#F3EFEA] text-[#1E1E22] border border-[#E8E3DC]'
                    }`}
                  >
                    {d.hoursLabel}
                  </div>
                )}

                {/* Vertical Pill Bar (border-radius: 9999px) */}
                <div className="w-full max-w-[28px] h-full flex items-end">
                  <div
                    style={{ height: `${heightPercent}%` }}
                    className={`w-full rounded-full transition-all duration-300 relative overflow-hidden ${
                      isPeak
                        ? 'bg-gradient-to-t from-[#F4B33E] to-[#F06A42] shadow-[0_4px_12px_rgba(244,179,62,0.3)]'
                        : isSelected
                        ? 'bg-[#1E1E22]'
                        : 'bg-[#F3EFEA] group-hover:bg-[#ECE7E1]'
                    }`}
                  >
                    {/* Micro shimmer line inside bar */}
                    <div className="absolute top-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-white/40" />
                  </div>
                </div>

                {/* Day Label & Date */}
                <div className="mt-2 text-center">
                  <span
                    className={`text-[11px] font-stat block transition-colors ${
                      isSelected || isPeak
                        ? 'text-[#1E1E22] font-bold'
                        : 'text-[#6E6B68]'
                    }`}
                  >
                    {d.day}
                  </span>
                  <span className="text-[9px] text-[#6E6B68] block -mt-0.5">
                    {d.tasksCount}t
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected Day Telemetry Footer */}
      <div className="pt-3 border-t border-[#E8E3DC]/60 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 text-[#6E6B68]">
          <Clock className="w-3.5 h-3.5 text-[#F4B33E]" />
          <span>
            {selectedDay} Total:{' '}
            <strong className="font-stat text-[#1E1E22]">
              {workloadDays.find((d) => d.day === selectedDay)?.hoursLabel}
            </strong>
          </span>
        </div>
        <span className="text-[11px] font-stat font-medium text-[#6E6B68] bg-[#F3EFEA] px-2 py-0.5 rounded-full">
          Weekly Avg: 4h 12m/d
        </span>
      </div>
    </div>
  );
};
