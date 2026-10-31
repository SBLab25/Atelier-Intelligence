"use client";

import React, { useState, useEffect } from 'react';
import { Search, X, CheckSquare, BarChart2, Clock, ArrowRight, BrainCircuit } from 'lucide-react';
import { Task, TeamMember, NavigationTab } from '../../types';

interface SearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  tasks: Task[];
  teamMembers: TeamMember[];
  onSelectTask: (taskId: string) => void;
  onTabChange: (tab: NavigationTab) => void;
}

export const SearchModal: React.FC<SearchModalProps> = ({
  isOpen,
  onClose,
  tasks,
  teamMembers,
  onSelectTask,
  onTabChange,
}) => {
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        // handled in parent or toggle
      }
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!isOpen) return null;

  const matchedTasks = tasks.filter((t) =>
    t.title.toLowerCase().includes(query.toLowerCase())
  );

  const matchedMembers = teamMembers.filter((m) =>
    m.name.toLowerCase().includes(query.toLowerCase()) ||
    m.role.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className="w-full max-w-xl bg-white rounded-[28px] p-4 shadow-[0_24px_50px_-12px_rgba(0,0,0,0.3)] border border-[#ECE7E1] overflow-hidden"
        role="dialog"
        aria-modal="true"
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 px-3 py-2 bg-[#F3EFEA] rounded-full border border-[#E8E3DC]">
          <Search className="w-4 h-4 text-[#6E6B68]" />
          <input
            type="text"
            autoFocus
            placeholder="Search deliverables, operators, telemetry, or commands..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-transparent text-xs text-[#1E1E22] placeholder:text-[#6E6B68] focus:outline-none"
          />
          {query ? (
            <button
              onClick={() => setQuery('')}
              className="text-[#6E6B68] hover:text-[#1E1E22]"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          ) : (
            <kbd className="font-stat text-[10px] bg-white text-[#6E6B68] px-1.5 py-0.5 rounded border border-[#E8E3DC]">
              ESC
            </kbd>
          )}
        </div>

        {/* Results List */}
        <div className="mt-4 max-h-80 overflow-y-auto space-y-4 px-1">
          {/* Quick Navigation Targets */}
          <div>
            <span className="text-[10px] font-stat uppercase tracking-wider text-[#6E6B68] px-2 block mb-1">
              Cockpit Views
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { tab: 'overview' as NavigationTab, label: 'Overview Bento Grid', icon: <BarChart2 className="w-3.5 h-3.5" /> },
                { tab: 'analytics' as NavigationTab, label: 'Quantitative Telemetry', icon: <BarChart2 className="w-3.5 h-3.5" /> },
                { tab: 'connections' as NavigationTab, label: 'Client Connections Hub', icon: <BrainCircuit className="w-3.5 h-3.5" /> },
                { tab: 'intelligence' as NavigationTab, label: 'Intelligence Hub & Modeling', icon: <BrainCircuit className="w-3.5 h-3.5" /> },
                { tab: 'time' as NavigationTab, label: 'Precision Time Dial', icon: <Clock className="w-3.5 h-3.5" /> },
                { tab: 'projects' as NavigationTab, label: 'Sprint Milestones', icon: <CheckSquare className="w-3.5 h-3.5" /> },
              ].map((v) => (
                <button
                  key={v.tab}
                  onClick={() => {
                    onTabChange(v.tab);
                    onClose();
                  }}
                  className="flex items-center justify-between p-2 rounded-xl hover:bg-[#FAF8F5] text-left border border-transparent hover:border-[#E8E3DC] transition-colors"
                >
                  <div className="flex items-center gap-2 text-xs font-medium text-[#1E1E22]">
                    <span className="text-[#F4B33E]">{v.icon}</span>
                    <span>{v.label}</span>
                  </div>
                  <ArrowRight className="w-3 h-3 text-[#6E6B68]" />
                </button>
              ))}
            </div>
          </div>

          {/* Deliverables */}
          {matchedTasks.length > 0 && (
            <div>
              <span className="text-[10px] font-stat uppercase tracking-wider text-[#6E6B68] px-2 block mb-1">
                Deliverables ({matchedTasks.length})
              </span>
              <div className="space-y-1">
                {matchedTasks.slice(0, 4).map((t) => (
                  <button
                    key={t.id}
                    onClick={() => {
                      onSelectTask(t.id);
                      onTabChange('time');
                      onClose();
                    }}
                    className="w-full flex items-center justify-between p-2 rounded-xl hover:bg-[#FAF8F5] text-left transition-colors group"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-2 h-2 rounded-full bg-[#F4B33E]" />
                      <span className="text-xs font-medium text-[#1E1E22] truncate group-hover:text-[#F4B33E]">
                        {t.title}
                      </span>
                    </div>
                    <span className="text-[10px] font-stat text-[#6E6B68] shrink-0 uppercase ml-2">
                      {t.category}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Team Members */}
          {matchedMembers.length > 0 && (
            <div>
              <span className="text-[10px] font-stat uppercase tracking-wider text-[#6E6B68] px-2 block mb-1">
                Team Operators ({matchedMembers.length})
              </span>
              <div className="space-y-1">
                {matchedMembers.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => {
                      onTabChange('team');
                      onClose();
                    }}
                    className="w-full flex items-center justify-between p-2 rounded-xl hover:bg-[#FAF8F5] text-left transition-colors"
                  >
                    <div className="flex items-center gap-2.5">
                      {m.avatar ? (
                        <img
                          src={m.avatar}
                          alt={m.name}
                          className="w-6 h-6 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-primary-container text-on-primary flex items-center justify-center text-[10px] font-bold">
                          {m.name.charAt(0) || 'M'}
                        </div>
                      )}
                      <div>
                        <span className="text-xs font-medium text-[#1E1E22] block leading-none">
                          {m.name}
                        </span>
                        <span className="text-[10px] text-[#6E6B68]">{m.role}</span>
                      </div>
                    </div>
                    <span className="text-[10px] font-stat text-[#449E74]">
                      {m.hoursLogged}h logged
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
