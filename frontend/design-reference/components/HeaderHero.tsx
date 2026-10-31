import React from 'react';
import { Calendar, ArrowUpRight, Plus, Sparkles, TrendingUp } from 'lucide-react';
import { UserProfile } from '../types';

interface HeaderHeroProps {
  user: UserProfile;
  onNewTask: () => void;
  onViewAnalytics: () => void;
}

export const HeaderHero: React.FC<HeaderHeroProps> = ({
  user,
  onNewTask,
  onViewAnalytics,
}) => {
  return (
    <div className="mb-6 relative rounded-[32px] overflow-hidden border border-[#ECE7E1] bg-white p-6 sm:p-8 shadow-[0_16px_36px_-12px_rgba(180,160,140,0.15)]">
      {/* Sunlit radial ambient glow */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at 85% 0%, rgba(254, 237, 188, 0.5) 0%, rgba(250, 248, 245, 0) 70%)',
        }}
      />

      <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
        <div className="max-w-2xl">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="font-stat text-[11px] uppercase tracking-widest text-[#6E6B68] font-semibold bg-[#F3EFEA] px-2.5 py-1 rounded-full border border-[#E8E3DC]">
              Sprint 42 · Week 4 · Q4 Velocity
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-stat font-medium text-[#449E74] bg-[#449E74]/10 px-2.5 py-1 rounded-full">
              <TrendingUp className="w-3 h-3" />
              +24% Ahead of Target
            </span>
          </div>

          <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tight text-[#1E1E22] leading-tight">
            Good morning, {user.name.split(' ')[0]}.
          </h1>
          <p className="text-sm sm:text-base text-[#6E6B68] mt-1.5 leading-relaxed font-normal">
            Your team reached <span className="font-semibold text-[#1E1E22]">94.2% precision milestone completion</span>. Three high-priority bento sprints are currently in flight.
          </p>
        </div>

        {/* Action Pills */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={onNewTask}
            className="flex items-center gap-2 bg-[#1E1E22] hover:bg-[#2E2E34] text-white px-5 py-2.5 rounded-full text-xs font-semibold tracking-tight shadow-md transition-all hover:-translate-y-0.5 active:translate-y-0"
          >
            <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
            <span>Create Sprint Task</span>
          </button>

          <button
            onClick={onViewAnalytics}
            className="flex items-center gap-2 bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] px-4 py-2.5 rounded-full text-xs font-semibold tracking-tight border border-[#E8E3DC] transition-all"
          >
            <Sparkles className="w-3.5 h-3.5 text-[#F4B33E]" />
            <span>Telemetry Report</span>
            <ArrowUpRight className="w-3.5 h-3.5 text-[#6E6B68]" />
          </button>
        </div>
      </div>
    </div>
  );
};
