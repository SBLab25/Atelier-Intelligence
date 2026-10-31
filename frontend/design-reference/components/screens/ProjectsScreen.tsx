import React, { useState } from 'react';
import { Task, TaskPriority, TaskCategory, TaskStatus } from '../../types';
import { Plus, Check, Clock, Filter, ArrowRight, Tag } from 'lucide-react';

interface ProjectsScreenProps {
  tasks: Task[];
  onToggleTask: (taskId: string) => void;
  onUpdateStatus: (taskId: string, status: TaskStatus) => void;
  onNewTask: () => void;
}

export const ProjectsScreen: React.FC<ProjectsScreenProps> = ({
  tasks,
  onToggleTask,
  onUpdateStatus,
  onNewTask,
}) => {
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const filteredTasks = tasks.filter((t) => {
    const matchCat = filterCategory === 'all' || t.category === filterCategory;
    const matchSearch = t.title.toLowerCase().includes(searchQuery.toLowerCase());
    return matchCat && matchSearch;
  });

  const columns: { id: TaskStatus; label: string; count: number; accent: string }[] = [
    {
      id: 'todo',
      label: 'Sprint Backlog',
      count: filteredTasks.filter((t) => !t.completed && t.status === 'todo').length,
      accent: '#6E6B68',
    },
    {
      id: 'in_progress',
      label: 'In Flight (Active)',
      count: filteredTasks.filter((t) => !t.completed && t.status === 'in_progress').length,
      accent: '#F4B33E',
    },
    {
      id: 'done',
      label: 'Shipped & Verified',
      count: filteredTasks.filter((t) => t.completed || t.status === 'done').length,
      accent: '#449E74',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-white rounded-[28px] border border-[#ECE7E1] shadow-[0_12px_28px_-8px_rgba(180,160,140,0.14)]">
        <div>
          <span className="font-stat text-[11px] uppercase tracking-wider text-[#6E6B68] bg-[#F3EFEA] px-2.5 py-0.5 rounded-full">
            Sprint Execution Board
          </span>
          <h2 className="text-2xl font-bold tracking-tight text-[#1E1E22] mt-1">
            Bento Projects & Milestones
          </h2>
          <p className="text-xs text-[#6E6B68]">
            Modular cards organized by delivery lifecycle stages.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <input
            type="text"
            placeholder="Filter tasks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-[#F3EFEA] border border-[#E8E3DC] rounded-full px-3.5 py-1.5 text-xs text-[#1E1E22] placeholder:text-[#6E6B68] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
          />

          {/* New Task Button */}
          <button
            onClick={onNewTask}
            className="flex items-center gap-1.5 bg-[#1E1E22] hover:bg-[#2E2E34] text-white px-4 py-2 rounded-full text-xs font-semibold shadow-sm transition-all hover:-translate-y-0.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Deliverable</span>
          </button>
        </div>
      </div>

      {/* Filter Category Chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {['all', 'core', 'analytics', 'review', 'client'].map((cat) => (
          <button
            key={cat}
            onClick={() => setFilterCategory(cat)}
            className={`px-3.5 py-1.5 rounded-full text-xs font-stat capitalize transition-all ${
              filterCategory === cat
                ? 'bg-[#1E1E22] text-white shadow-xs font-medium'
                : 'bg-white text-[#6E6B68] hover:text-[#1E1E22] border border-[#E8E3DC]'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 3-Column Bento Kanban Board */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {columns.map((col) => {
          const colTasks = filteredTasks.filter((t) => {
            if (col.id === 'done') return t.completed || t.status === 'done';
            return !t.completed && t.status === col.id;
          });

          return (
            <div key={col.id} className="flex flex-col gap-3">
              {/* Column Header */}
              <div className="flex items-center justify-between px-3 py-2 bg-[#F3EFEA] rounded-2xl border border-[#E8E3DC]">
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: col.accent }}
                  />
                  <h3 className="text-xs font-bold text-[#1E1E22] tracking-tight">
                    {col.label}
                  </h3>
                </div>
                <span className="font-stat text-xs font-semibold bg-white px-2 py-0.5 rounded-full text-[#1E1E22] shadow-xs">
                  {colTasks.length}
                </span>
              </div>

              {/* Tasks List in Column */}
              <div className="space-y-3 min-h-[400px]">
                {colTasks.map((t) => (
                  <div
                    key={t.id}
                    className="bento-card p-4 bg-white flex flex-col justify-between group hover:border-[#F4B33E] transition-all"
                  >
                    <div>
                      {/* Priority Tag & Category */}
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-stat uppercase bg-[#F3EFEA] text-[#6E6B68] px-2 py-0.5 rounded-full">
                          {t.category}
                        </span>

                        <span
                          className={`text-[9px] font-stat font-semibold uppercase px-2 py-0.5 rounded-full ${
                            t.priority === 'high'
                              ? 'bg-[#F06A42]/15 text-[#F06A42]'
                              : t.priority === 'medium'
                              ? 'bg-[#F4B33E]/20 text-[#1E1E22]'
                              : 'bg-[#C8C5CB]/30 text-[#6E6B68]'
                          }`}
                        >
                          {t.priority}
                        </span>
                      </div>

                      {/* Title */}
                      <h4
                        onClick={() => onToggleTask(t.id)}
                        className={`text-xs font-semibold cursor-pointer transition-colors leading-snug ${
                          t.completed ? 'line-through text-[#6E6B68]' : 'text-[#1E1E22] group-hover:text-[#F4B33E]'
                        }`}
                      >
                        {t.title}
                      </h4>
                    </div>

                    {/* Footer: Due date, Assignee, Next stage action */}
                    <div className="mt-4 pt-3 border-t border-[#E8E3DC]/60 flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <img
                          src={t.assignee.avatar}
                          alt={t.assignee.name}
                          title={t.assignee.name}
                          className="w-6 h-6 rounded-full object-cover ring-1 ring-[#E8E3DC]"
                        />
                        <span className="text-[11px] font-stat text-[#6E6B68]">
                          {t.spentMinutes}m / {t.estimatedMinutes}m
                        </span>
                      </div>

                      {/* State transition button */}
                      <div className="flex items-center gap-1.5">
                        {col.id === 'todo' && (
                          <button
                            onClick={() => onUpdateStatus(t.id, 'in_progress')}
                            className="text-[10px] font-stat font-semibold bg-[#F3EFEA] hover:bg-[#1E1E22] hover:text-white text-[#1E1E22] px-2.5 py-1 rounded-full transition-all flex items-center gap-1"
                            title="Move to In Flight"
                          >
                            <span>Start</span>
                            <ArrowRight className="w-3 h-3" />
                          </button>
                        )}
                        {col.id === 'in_progress' && (
                          <button
                            onClick={() => onToggleTask(t.id)}
                            className="text-[10px] font-stat font-semibold bg-[#F4B33E] hover:bg-[#e5a532] text-[#1E1E22] px-2.5 py-1 rounded-full transition-all flex items-center gap-1 shadow-xs"
                            title="Mark Completed"
                          >
                            <Check className="w-3 h-3 stroke-[2.5]" />
                            <span>Complete</span>
                          </button>
                        )}
                        {col.id === 'done' && (
                          <span className="text-[10px] font-stat font-medium text-[#449E74] flex items-center gap-1">
                            <Check className="w-3 h-3" />
                            Shipped
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {colTasks.length === 0 && (
                  <div className="h-32 border-2 border-dashed border-[#E8E3DC] rounded-2xl flex items-center justify-center text-xs text-[#6E6B68]">
                    No deliverables in this stage
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
