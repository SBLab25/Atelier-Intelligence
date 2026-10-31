"use client";

import React, { useState } from 'react';
import { Clock, ArrowUpRight, Plus } from 'lucide-react';
import { ScheduleEvent } from '../../types';

interface CalendarTimelineStripProps {
  events: ScheduleEvent[];
  onAddEvent?: () => void;
  onExpandView?: () => void;
}

export const CalendarTimelineStrip: React.FC<CalendarTimelineStripProps> = ({
  events,
  onAddEvent,
  onExpandView,
}) => {
  const [selectedDayIndex, setSelectedDayIndex] = useState<number>(2); // Wednesday Oct 28 (Today)

  const days = [
    { day: 'Mon', date: '26', full: 'Oct 26' },
    { day: 'Tue', date: '27', full: 'Oct 27' },
    { day: 'Wed', date: '28', full: 'Oct 28', isToday: true },
    { day: 'Thu', date: '29', full: 'Oct 29' },
    { day: 'Fri', date: '30', full: 'Oct 30' },
    { day: 'Sat', date: '31', full: 'Oct 31' },
    { day: 'Sun', date: '01', full: 'Nov 01' },
  ];

  return (
    <div className="bento-card p-6 flex flex-col justify-between bg-white relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <span className="text-[11px] font-stat uppercase tracking-wider text-[#6E6B68] block">
            Tactile Schedule
          </span>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-[#1E1E22] tracking-tight">
              Calendar Timeline Strip
            </h3>
            <span className="text-xs text-[#6E6B68]">
              {events.length} sessions scheduled
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onAddEvent && (
            <button
              onClick={onAddEvent}
              className="flex items-center gap-1 bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] px-2.5 py-1 rounded-full text-xs font-medium transition-colors border border-[#E8E3DC]"
              aria-label="Add new schedule block"
            >
              <Plus className="w-3 h-3 text-[#1E1E22]" />
              <span className="text-[11px]">Add Slot</span>
            </button>
          )}
          {onExpandView && (
            <button
              onClick={onExpandView}
              className="w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] flex items-center justify-center transition-colors shadow-xs"
              aria-label="Expand calendar timeline"
            >
              <ArrowUpRight className="w-4 h-4 text-[#1E1E22]" />
            </button>
          )}
        </div>
      </div>

      {/* Integrated Horizontal Day-Picker with Active Day Capsule Highlighting */}
      <div className="flex items-center justify-between gap-1.5 p-1.5 bg-[#F3EFEA] rounded-2xl border border-[#E8E3DC] mb-4 overflow-x-auto">
        {days.map((item, idx) => {
          const isSelected = selectedDayIndex === idx;
          return (
            <button
              key={idx}
              onClick={() => setSelectedDayIndex(idx)}
              className={`flex-1 min-w-[42px] py-2 px-1 rounded-xl text-center transition-all duration-200 flex flex-col items-center justify-center ${
                isSelected
                  ? 'bg-[#1E1E22] text-white shadow-sm'
                  : 'text-[#6E6B68] hover:text-[#1E1E22] hover:bg-[#FAF8F5]'
              }`}
              aria-label={`Select ${item.day} ${item.full}`}
            >
              <span className="text-[10px] font-stat uppercase tracking-wider block">
                {item.day}
              </span>
              <span
                className={`font-stat text-sm font-bold block mt-0.5 ${
                  isSelected ? 'text-[#F4B33E]' : item.isToday ? 'text-[#F06A42]' : ''
                }`}
              >
                {item.date}
              </span>
              {item.isToday && !isSelected && (
                <span className="w-1 h-1 rounded-full bg-[#F06A42] mt-0.5" />
              )}
            </button>
          );
        })}
      </div>

      {/* Schedule Blocks with Grouped Avatar Stacks and Project Tags */}
      <div className="space-y-2.5">
        {events.map((ev) => (
          <div
            key={ev.id}
            className="flex items-center justify-between p-3 rounded-2xl bg-[#FAF8F5] border border-[#E8E3DC] hover:border-[#C8C5CB] transition-all group"
          >
            <div className="flex items-start gap-3 min-w-0">
              <span
                className="w-2 h-10 rounded-full shrink-0 mt-0.5"
                style={{ backgroundColor: ev.tagColor }}
              />
              <div className="min-w-0">
                <h4 className="text-xs font-semibold text-[#1E1E22] truncate group-hover:text-[#F06A42] transition-colors">
                  {ev.title}
                </h4>
                <div className="flex items-center gap-2 mt-1 text-[11px] text-[#6E6B68]">
                  <span className="flex items-center gap-1 font-stat">
                    <Clock className="w-3 h-3 text-[#6E6B68]" />
                    {ev.time}
                  </span>
                  <span>•</span>
                  <span className="font-medium text-[#1E1E22] bg-[#F3EFEA] px-2 py-0.2 rounded-full text-[10px]">
                    {ev.category}
                  </span>
                </div>
              </div>
            </div>

            {/* Grouped Avatar Stack */}
            <div className="flex items-center -space-x-2 shrink-0 pl-2">
              {ev.attendees.map((att, aIdx) => (
                att.avatar ? (
                  <img
                    key={aIdx}
                    src={att.avatar}
                    alt={att.name}
                    title={att.name}
                    className="w-7 h-7 rounded-full object-cover ring-2 ring-white shadow-xs"
                  />
                ) : (
                  <div
                    key={aIdx}
                    title={att.name}
                    className="w-7 h-7 rounded-full bg-primary-container text-on-primary ring-2 ring-white shadow-xs flex items-center justify-center text-[10px] font-bold"
                  >
                    {att.name.charAt(0) || 'A'}
                  </div>
                )
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
