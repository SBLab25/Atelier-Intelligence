import React from 'react';
import { Check, ArrowUpRight, Sparkles } from 'lucide-react';
import { Task } from '../../types';
import { calculateTaskStats } from '../../utils/bentoMetrics';

interface InvertedFocusModuleProps {
  tasks: Task[];
  onToggleTask: (taskId: string) => void;
  onExpandView?: () => void;
}

export const InvertedFocusModule: React.FC<InvertedFocusModuleProps> = ({
  tasks,
  onToggleTask,
  onExpandView,
}) => {
  const stats = calculateTaskStats(tasks);

  return (
    <div className="bento-card-dark p-6 flex flex-col justify-between text-white relative overflow-hidden">
      {/* Ghost glow accent */}
      <div className="absolute top-0 right-0 w-36 h-36 bg-[#F4B33E]/10 rounded-full blur-3xl pointer-events-none" />

      {/* Header */}
      <div className="flex items-start justify-between mb-4 relative z-10">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-stat uppercase tracking-widest text-[#F4B33E] font-medium bg-[#F4B33E]/15 px-2 py-0.5 rounded-full">
              CRITICAL PATH
            </span>
            <Sparkles className="w-3.5 h-3.5 text-[#F4B33E]" />
          </div>
          <h3 className="text-lg font-semibold tracking-tight text-white">
            Sprint Focus & Deliverables
          </h3>
          <p className="text-xs text-[#87858A] mt-0.5">
            Key operational milestones for Week 4
          </p>
        </div>

        {onExpandView && (
          <button
            onClick={onExpandView}
            className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors shadow-xs"
            aria-label="Expand deliverables view"
          >
            <ArrowUpRight className="w-4 h-4 text-white" />
          </button>
        )}
      </div>

      {/* Space Grotesk Counters */}
      <div className="grid grid-cols-3 gap-2 py-3 px-4 bg-white/[0.04] rounded-2xl border border-white/[0.06] mb-4">
        <div>
          <span className="text-[10px] font-stat uppercase tracking-wider text-[#87858A] block">
            Completed
          </span>
          <span className="font-stat text-2xl font-bold text-white tabular-nums">
            {stats.completed}
            <span className="text-xs font-normal text-[#87858A]">/{stats.total}</span>
          </span>
        </div>
        <div>
          <span className="text-[10px] font-stat uppercase tracking-wider text-[#87858A] block">
            Velocity
          </span>
          <span className="font-stat text-2xl font-bold text-[#F4B33E] tabular-nums">
            {stats.percentCompleted}%
          </span>
        </div>
        <div>
          <span className="text-[10px] font-stat uppercase tracking-wider text-[#87858A] block">
            Remaining
          </span>
          <span className="font-stat text-2xl font-bold text-white tabular-nums">
            {stats.pending}
          </span>
        </div>
      </div>

      {/* Task List with Circular Check Tokens */}
      <div className="space-y-2 mb-4 relative z-10 flex-1 overflow-y-auto max-h-[220px] pr-1">
        {tasks.map((task) => (
          <div
            key={task.id}
            onClick={() => onToggleTask(task.id)}
            className="group flex items-start gap-3 p-2.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.04] transition-all cursor-pointer"
          >
            {/* Circular Check Token: Filled Amber Gold disc with dark check when completed, hollow ring when pending */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleTask(task.id);
              }}
              className={`mt-0.5 w-5 h-5 rounded-full flex items-center justify-center transition-all shrink-0 ${
                task.completed
                  ? 'bg-[#F4B33E] text-[#1E1E22] ring-2 ring-[#F4B33E]/50'
                  : 'border-2 border-[#87858A] hover:border-[#F4B33E] bg-transparent'
              }`}
              aria-label={task.completed ? `Mark "${task.title}" as pending` : `Mark "${task.title}" as completed`}
            >
              {task.completed && <Check className="w-3 h-3 stroke-[3]" />}
            </button>

            <div className="flex-1 min-w-0">
              <span
                className={`text-xs block font-medium leading-snug transition-colors ${
                  task.completed
                    ? 'line-through text-[#87858A]'
                    : 'text-white group-hover:text-[#F4B33E]'
                }`}
              >
                {task.title}
              </span>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] font-stat text-[#87858A] uppercase">
                  {task.category}
                </span>
                <span className="text-[#87858A] text-[10px]">•</span>
                <span className="text-[10px] font-stat text-[#87858A]">
                  Est: {task.estimatedMinutes}m
                </span>
                {task.priority === 'high' && (
                  <span className="text-[9px] font-stat font-semibold bg-[#F06A42]/20 text-[#F06A42] px-1.5 py-0.2 rounded-full uppercase">
                    High
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom Progress Bar */}
      <div className="pt-2 border-t border-white/[0.08] relative z-10">
        <div className="flex justify-between items-center text-[10px] font-stat text-[#87858A] mb-1.5">
          <span>Sprint Completion Pace</span>
          <span className="text-[#F4B33E] font-medium">{stats.percentCompleted}% of milestones</span>
        </div>
        <div className="w-full h-2 rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-[#F4B33E] to-[#F06A42] rounded-full transition-all duration-500"
            style={{ width: `${stats.percentCompleted}%` }}
          />
        </div>
      </div>
    </div>
  );
};
