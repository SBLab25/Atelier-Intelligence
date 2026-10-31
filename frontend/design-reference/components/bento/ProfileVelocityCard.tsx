import React from 'react';
import { UserProfile } from '../../types';
import { Sparkles, ArrowUpRight, Target, ShieldCheck } from 'lucide-react';

interface ProfileVelocityCardProps {
  user: UserProfile;
  completedTasksCount: number;
  totalTasksCount: number;
  onExpandView?: () => void;
}

export const ProfileVelocityCard: React.FC<ProfileVelocityCardProps> = ({
  user,
  completedTasksCount,
  totalTasksCount,
  onExpandView,
}) => {
  const completionPercentage = totalTasksCount > 0 ? Math.round((completedTasksCount / totalTasksCount) * 100) : 0;

  return (
    <div className="bento-card p-6 flex flex-col justify-between bg-white relative overflow-hidden">
      {/* Sunlit subtle ambient shimmer in corner */}
      <div className="absolute top-0 right-0 w-40 h-40 bg-radial from-[#FEEDB8]/30 to-transparent pointer-events-none rounded-full blur-2xl" />

      {/* Header & Status */}
      <div className="flex items-start justify-between relative z-10 mb-4">
        <div className="flex items-center gap-3">
          <div className="relative">
            <img
              src={user.avatar}
              alt={user.name}
              className="w-14 h-14 rounded-full object-cover ring-4 ring-[#FAF8F5] shadow-sm"
            />
            <span className="absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-[#449E74] ring-2 ring-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-[#1E1E22] tracking-tight">
                {user.name}
              </h2>
              <span className="inline-flex items-center gap-1 text-[10px] font-stat font-semibold bg-[#449E74]/15 text-[#449E74] px-2 py-0.5 rounded-full">
                <ShieldCheck className="w-3 h-3" />
                {user.status}
              </span>
            </div>
            <p className="text-xs text-[#6E6B68] mt-0.5">{user.role}</p>
          </div>
        </div>

        {onExpandView && (
          <button
            onClick={onExpandView}
            className="w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] flex items-center justify-center transition-colors shadow-xs"
            aria-label="Expand profile metrics"
          >
            <ArrowUpRight className="w-4 h-4 text-[#1E1E22]" />
          </button>
        )}
      </div>

      {/* Velocity and Sprint Capacity Metrics */}
      <div className="space-y-3 relative z-10 my-auto py-2">
        <div className="p-3.5 bg-[#FAF8F5] rounded-2xl border border-[#E8E3DC]">
          <div className="flex justify-between items-center text-xs mb-1.5">
            <span className="text-[#6E6B68] flex items-center gap-1.5 font-medium">
              <Target className="w-3.5 h-3.5 text-[#F4B33E]" />
              Sprint 42 Velocity
            </span>
            <span className="font-stat text-sm font-bold text-[#1E1E22]">
              {user.weeklyVelocity} <span className="text-[11px] font-normal text-[#6E6B68]">/ {user.sprintTarget} pts</span>
            </span>
          </div>

          <div className="w-full h-2 rounded-full bg-[#E8E3DC] overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-[#F4B33E] to-[#F06A42] rounded-full transition-all duration-500"
              style={{ width: `${(user.weeklyVelocity / user.sprintTarget) * 100}%` }}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-3 bg-[#F3EFEA] rounded-xl border border-[#E8E3DC]/60">
            <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
              Deliverables
            </span>
            <span className="font-stat text-lg font-bold text-[#1E1E22] mt-0.5 block">
              {completedTasksCount} / {totalTasksCount}
            </span>
            <span className="text-[10px] text-[#449E74] font-medium">
              {completionPercentage}% complete
            </span>
          </div>

          <div className="p-3 bg-[#F3EFEA] rounded-xl border border-[#E8E3DC]/60">
            <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
              Focus Ratio
            </span>
            <span className="font-stat text-lg font-bold text-[#1E1E22] mt-0.5 block">
              4.6 <span className="text-xs font-normal text-[#6E6B68]">hrs/day</span>
            </span>
            <span className="text-[10px] text-[#F4B33E] font-medium">
              Top 5% of Org
            </span>
          </div>
        </div>
      </div>

      {/* Tactile Mini Footer */}
      <div className="pt-3 border-t border-[#E8E3DC]/60 flex items-center justify-between text-xs text-[#6E6B68] relative z-10">
        <span className="flex items-center gap-1.5 text-[11px]">
          <Sparkles className="w-3.5 h-3.5 text-[#F4B33E]" />
          Deep focus active
        </span>
        <span className="font-stat text-[11px] bg-[#1E1E22] text-white px-2 py-0.5 rounded-full">
          Sprint W4
        </span>
      </div>
    </div>
  );
};
