import React from 'react';
import { TeamMember } from '../../types';
import { Mail, Shield, CheckCircle, Clock, ExternalLink } from 'lucide-react';

interface TeamScreenProps {
  members: TeamMember[];
  onAssignToMember: (memberId: string) => void;
}

export const TeamScreen: React.FC<TeamScreenProps> = ({ members, onAssignToMember }) => {
  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-white rounded-[28px] border border-[#ECE7E1] shadow-[0_12px_28px_-8px_rgba(180,160,140,0.14)]">
        <div>
          <span className="font-stat text-[11px] uppercase tracking-wider text-[#6E6B68] bg-[#F3EFEA] px-2.5 py-0.5 rounded-full">
            Human Resources & Capacity
          </span>
          <h2 className="text-2xl font-bold tracking-tight text-[#1E1E22] mt-1">
            Quantitative Team Roster
          </h2>
          <p className="text-xs text-[#6E6B68]">
            Resource allocations, weekly logged bandwidth, and assigned strategic epics.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-stat text-xs bg-[#FAF8F5] border border-[#E8E3DC] px-3.5 py-1.5 rounded-full font-semibold text-[#1E1E22]">
            {members.length} Active Operators
          </span>
        </div>
      </div>

      {/* Team Bento Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {members.map((m) => {
          const capacityPercent = Math.round((m.hoursLogged / m.capacityHours) * 100);

          return (
            <div
              key={m.id}
              className="bento-card p-6 bg-white flex flex-col justify-between hover:border-[#C8C5CB] transition-all"
            >
              {/* Member Top Info */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3.5">
                  <div className="relative">
                    <img
                      src={m.avatar}
                      alt={m.name}
                      className="w-14 h-14 rounded-full object-cover ring-2 ring-[#E8E3DC] shadow-sm"
                    />
                    <span className="absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-[#449E74] ring-2 ring-white" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[#1E1E22] tracking-tight">
                      {m.name}
                    </h3>
                    <p className="text-xs text-[#6E6B68]">{m.role}</p>
                    <span className="inline-block mt-1 font-stat text-[10px] text-[#449E74] font-medium bg-[#449E74]/10 px-2 py-0.2 rounded-full">
                      {m.status}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => onAssignToMember(m.id)}
                  className="w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#1E1E22] hover:text-white text-[#1E1E22] flex items-center justify-center transition-colors shadow-xs"
                  aria-label={`Assign task to ${m.name}`}
                  title="Assign Deliverable"
                >
                  <Mail className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Active Project Capsule */}
              <div className="my-4 p-3 bg-[#FAF8F5] rounded-2xl border border-[#E8E3DC]">
                <span className="text-[10px] font-stat uppercase text-[#6E6B68] block mb-0.5">
                  Current Focus Epic
                </span>
                <span className="text-xs font-semibold text-[#1E1E22] block">
                  {m.activeProject}
                </span>
              </div>

              {/* Bandwidth Capacity Progress */}
              <div>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="text-[#6E6B68] flex items-center gap-1 font-medium">
                    <Clock className="w-3 h-3 text-[#F4B33E]" />
                    Weekly Bandwidth
                  </span>
                  <span className="font-stat font-bold text-[#1E1E22]">
                    {m.hoursLogged}h{' '}
                    <span className="text-[10px] font-normal text-[#6E6B68]">
                      / {m.capacityHours}h ({capacityPercent}%)
                    </span>
                  </span>
                </div>

                <div className="w-full h-2 rounded-full bg-[#F3EFEA] overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      capacityPercent >= 90
                        ? 'bg-[#F06A42]'
                        : 'bg-[#F4B33E]'
                    }`}
                    style={{ width: `${Math.min(100, capacityPercent)}%` }}
                  />
                </div>
              </div>

              {/* Footer */}
              <div className="mt-4 pt-3 border-t border-[#E8E3DC]/60 flex items-center justify-between text-[11px] text-[#6E6B68]">
                <span>Availability: Full Time</span>
                <span className="font-stat text-[#1E1E22] font-medium">Sprint 42 Active</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
