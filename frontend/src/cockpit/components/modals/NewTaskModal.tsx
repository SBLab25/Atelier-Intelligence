"use client";

import React, { useState } from 'react';
import { X, Sparkles } from 'lucide-react';
import { TaskCategory, TaskPriority, TeamMember } from '../../types';

interface NewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddTask: (task: {
    title: string;
    category: TaskCategory;
    priority: TaskPriority;
    estimatedMinutes: number;
    assigneeId: string;
  }) => void;
  teamMembers: TeamMember[];
}

export const NewTaskModal: React.FC<NewTaskModalProps> = ({
  isOpen,
  onClose,
  onAddTask,
  teamMembers,
}) => {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<TaskCategory>('core');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [estimatedMinutes, setEstimatedMinutes] = useState(45);
  const [assigneeId, setAssigneeId] = useState(teamMembers[0]?.id || '');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    onAddTask({
      title: title.trim(),
      category,
      priority,
      estimatedMinutes,
      assigneeId,
    });
    setTitle('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        className="w-full max-w-lg bg-white rounded-[32px] p-6 sm:p-8 shadow-[0_24px_50px_-12px_rgba(0,0,0,0.25)] border border-[#ECE7E1] relative"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-headline"
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-6 right-6 w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] flex items-center justify-center transition-colors"
          aria-label="Close dialog"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 mb-1">
          <span className="font-stat text-[10px] uppercase tracking-wider text-[#F4B33E] font-semibold bg-[#F4B33E]/15 px-2.5 py-0.5 rounded-full">
            Sprint 42 Deliverable
          </span>
          <Sparkles className="w-3.5 h-3.5 text-[#F4B33E]" />
        </div>

        <h2 id="modal-headline" className="text-xl font-bold tracking-tight text-[#1E1E22]">
          Create New Bento Milestone
        </h2>
        <p className="text-xs text-[#6E6B68] mt-0.5">
          Define objective parameters, priority weighting, and estimated minutes.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-[#1E1E22] mb-1.5">
              Deliverable Title *
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Implement tactile feedback curves on dial widgets..."
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-[#FAF8F5] border border-[#E8E3DC] rounded-2xl px-4 py-2.5 text-xs text-[#1E1E22] placeholder:text-[#6E6B68] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-[#1E1E22] mb-1.5">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as TaskCategory)}
                className="w-full bg-[#FAF8F5] border border-[#E8E3DC] rounded-2xl px-3 py-2.5 text-xs text-[#1E1E22] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
              >
                <option value="core">Core Architecture</option>
                <option value="analytics">Quantitative Analytics</option>
                <option value="review">Ergonomics & Review</option>
                <option value="client">Client Project</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#1E1E22] mb-1.5">
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as TaskPriority)}
                className="w-full bg-[#FAF8F5] border border-[#E8E3DC] rounded-2xl px-3 py-2.5 text-xs text-[#1E1E22] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
              >
                <option value="high">High (Sprint Critical)</option>
                <option value="medium">Medium (Standard)</option>
                <option value="low">Low (Nice to have)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-[#1E1E22] mb-1.5">
                Estimate (Minutes)
              </label>
              <input
                type="number"
                min="10"
                max="600"
                step="5"
                value={estimatedMinutes}
                onChange={(e) => setEstimatedMinutes(Number(e.target.value))}
                className="w-full bg-[#FAF8F5] border border-[#E8E3DC] rounded-2xl px-3 py-2.5 text-xs font-stat text-[#1E1E22] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#1E1E22] mb-1.5">
                Assignee
              </label>
              <select
                value={assigneeId}
                onChange={(e) => setAssigneeId(e.target.value)}
                className="w-full bg-[#FAF8F5] border border-[#E8E3DC] rounded-2xl px-3 py-2.5 text-xs text-[#1E1E22] focus:outline-none focus:ring-2 focus:ring-[#F4B33E]"
              >
                {teamMembers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.role.split(' ')[0]})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="pt-4 flex items-center justify-end gap-3 border-t border-[#E8E3DC]">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-full text-xs font-semibold text-[#6E6B68] hover:bg-[#F3EFEA] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-6 py-2.5 rounded-full text-xs font-semibold bg-[#1E1E22] hover:bg-[#2E2E34] text-white shadow-sm transition-all hover:-translate-y-0.5 active:translate-y-0"
            >
              Add Deliverable
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
