import React, { useState } from 'react';
import { Play, Pause, RotateCcw, Clock, DollarSign, Tag, CheckCircle2, Trash2, Plus } from 'lucide-react';
import { Task, TimeLog } from '../../types';
import { formatDuration, formatHoursMinutes } from '../../utils/bentoMetrics';
import { TimeTrackerDial } from '../bento/TimeTrackerDial';

interface TimeOperationsScreenProps {
  tasks: Task[];
  activeTaskId: string;
  onSelectTask: (taskId: string) => void;
  timeLogs: TimeLog[];
  onLogTime: (taskId: string, durationSeconds: number) => void;
  onDeleteLog: (logId: string) => void;
}

export const TimeOperationsScreen: React.FC<TimeOperationsScreenProps> = ({
  tasks,
  activeTaskId,
  onSelectTask,
  timeLogs,
  onLogTime,
  onDeleteLog,
}) => {
  const [filterProject, setFilterProject] = useState<string>('all');
  const [manualMinutes, setManualMinutes] = useState<string>('30');
  const [manualNote, setManualNote] = useState<string>('');

  const activeTask = tasks.find((t) => t.id === activeTaskId) || tasks[0];

  const totalLoggedSeconds = timeLogs.reduce((acc, log) => acc + log.durationSeconds, 0);
  const billableSeconds = timeLogs
    .filter((l) => l.billable)
    .reduce((acc, l) => acc + l.durationSeconds, 0);

  const handleManualAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const mins = parseInt(manualMinutes, 10);
    if (!isNaN(mins) && mins > 0 && activeTask) {
      onLogTime(activeTask.id, mins * 60);
      setManualNote('');
    }
  };

  const filteredLogs = filterProject === 'all'
    ? timeLogs
    : timeLogs.filter((l) => l.project.toLowerCase().includes(filterProject.toLowerCase()));

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-white rounded-[28px] border border-[#ECE7E1] shadow-[0_12px_28px_-8px_rgba(180,160,140,0.14)]">
        <div>
          <span className="font-stat text-[11px] uppercase tracking-wider text-[#6E6B68] bg-[#F3EFEA] px-2.5 py-0.5 rounded-full">
            Time & Operations Cockpit
          </span>
          <h2 className="text-2xl font-bold tracking-tight text-[#1E1E22] mt-1">
            Precision Time Operations
          </h2>
          <p className="text-xs text-[#6E6B68]">
            High-cadence session tracker, billable allocation meters, and audit trails.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-[#FAF8F5] border border-[#E8E3DC] px-4 py-2 rounded-2xl text-right">
            <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
              Total Recorded
            </span>
            <span className="font-stat text-xl font-bold text-[#1E1E22] tabular-nums">
              {formatHoursMinutes(Math.round(totalLoggedSeconds / 60))}
            </span>
          </div>

          <div className="bg-[#FAF8F5] border border-[#E8E3DC] px-4 py-2 rounded-2xl text-right">
            <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
              Billable Ratio
            </span>
            <span className="font-stat text-xl font-bold text-[#F4B33E] tabular-nums">
              {totalLoggedSeconds > 0 ? Math.round((billableSeconds / totalLoggedSeconds) * 100) : 0}%
            </span>
          </div>
        </div>
      </div>

      {/* Main Grid: Interactive Dial & Quick Log Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Flagship Dial Module (6 cols) */}
        <div className="lg:col-span-6 flex flex-col">
          <TimeTrackerDial
            tasks={tasks}
            activeTaskId={activeTaskId}
            onSelectTask={onSelectTask}
            onLogTime={onLogTime}
          />
        </div>

        {/* Manual Time Entry & Settings Card (6 cols) */}
        <div className="lg:col-span-6 bento-card p-6 bg-white flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#F4B33E]" />
              <h3 className="text-base font-semibold text-[#1E1E22]">
                Manual Time Adjustment & Session Metadata
              </h3>
            </div>
            <p className="text-xs text-[#6E6B68]">
              Log completed off-dial sessions or review meetings with client tags.
            </p>

            <form onSubmit={handleManualAdd} className="mt-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#1E1E22] mb-1">
                  Target Sprint Deliverable
                </label>
                <div className="bg-[#F3EFEA] rounded-xl p-2.5 border border-[#E8E3DC]">
                  <span className="text-xs font-medium text-[#1E1E22]">
                    {activeTask.title}
                  </span>
                  <div className="flex items-center gap-2 mt-1 text-[10px] font-stat text-[#6E6B68]">
                    <span>Category: {activeTask.category}</span>
                    <span>•</span>
                    <span>Spent: {activeTask.spentMinutes}m / {activeTask.estimatedMinutes}m</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#1E1E22] mb-1">
                    Duration (Minutes)
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="600"
                    step="5"
                    value={manualMinutes}
                    onChange={(e) => setManualMinutes(e.target.value)}
                    className="w-full bg-[#F3EFEA] border border-[#E8E3DC] rounded-xl px-3 py-2 text-xs font-stat font-medium text-[#1E1E22] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#1E1E22] mb-1">
                    Billing Status
                  </label>
                  <div className="flex items-center gap-2 bg-[#F3EFEA] border border-[#E8E3DC] rounded-xl px-3 py-2 text-xs text-[#1E1E22]">
                    <DollarSign className="w-4 h-4 text-[#449E74]" />
                    <span className="font-medium">Client Billable</span>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#1E1E22] mb-1">
                  Session Notes & Context
                </label>
                <input
                  type="text"
                  placeholder="e.g. Tactile ergonomics audit notes..."
                  value={manualNote}
                  onChange={(e) => setManualNote(e.target.value)}
                  className="w-full bg-[#F3EFEA] border border-[#E8E3DC] rounded-xl px-3 py-2 text-xs text-[#1E1E22] placeholder:text-[#6E6B68] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
                />
              </div>

              <button
                type="submit"
                className="w-full bg-[#1E1E22] hover:bg-[#2E2E34] text-white py-2.5 px-4 rounded-full text-xs font-semibold shadow-sm transition-all flex items-center justify-center gap-2"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Log Session to Sprint</span>
              </button>
            </form>
          </div>

          <div className="mt-4 pt-3 border-t border-[#E8E3DC] flex items-center justify-between text-xs text-[#6E6B68]">
            <span>Active Sprint Target: 40h/week</span>
            <span className="font-stat font-medium text-[#449E74]">On Track</span>
          </div>
        </div>
      </div>

      {/* Session History Audit Ledger */}
      <div className="bento-card p-6 bg-white">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-base font-semibold text-[#1E1E22]">
              Recorded Sessions Ledger
            </h3>
            <p className="text-xs text-[#6E6B68]">
              Verified time intervals logged into sprint telemetries
            </p>
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-1.5 bg-[#F3EFEA] p-1 rounded-full border border-[#E8E3DC]">
            {['all', 'Aura', 'Warm Tactile', 'Typography'].map((proj) => (
              <button
                key={proj}
                onClick={() => setFilterProject(proj)}
                className={`px-3 py-1 rounded-full text-xs font-stat capitalize transition-all ${
                  filterProject === proj
                    ? 'bg-[#1E1E22] text-white shadow-xs'
                    : 'text-[#6E6B68] hover:text-[#1E1E22]'
                }`}
              >
                {proj}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2.5">
          {filteredLogs.map((log) => (
            <div
              key={log.id}
              className="flex items-center justify-between p-3 rounded-2xl bg-[#FAF8F5] border border-[#E8E3DC] hover:border-[#C8C5CB] transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-[#F3EFEA] flex items-center justify-center text-[#F4B33E]">
                  <Clock className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-[#1E1E22]">
                    {log.taskTitle}
                  </h4>
                  <div className="flex items-center gap-2 mt-0.5 text-[11px] text-[#6E6B68]">
                    <span className="font-medium text-[#1E1E22] bg-[#F3EFEA] px-2 py-0.2 rounded-full text-[10px]">
                      {log.project}
                    </span>
                    <span>•</span>
                    <span className="font-stat">{log.timestamp}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="text-right">
                  <span className="font-stat text-sm font-bold text-[#1E1E22] block">
                    {formatDuration(log.durationSeconds)}
                  </span>
                  <span className="text-[10px] font-stat text-[#449E74] block">
                    {log.billable ? 'Billable' : 'Internal'}
                  </span>
                </div>

                <button
                  onClick={() => onDeleteLog(log.id)}
                  className="w-8 h-8 rounded-full bg-white hover:bg-[#F06A42]/10 text-[#6E6B68] hover:text-[#F06A42] flex items-center justify-center transition-colors border border-[#E8E3DC]"
                  aria-label="Delete time log entry"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
