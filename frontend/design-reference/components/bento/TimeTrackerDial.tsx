import React, { useState, useEffect } from 'react';
import { Play, Pause, RotateCcw, Tag, ArrowUpRight } from 'lucide-react';
import { formatDuration } from '../../utils/bentoMetrics';
import { Task } from '../../types';

interface TimeTrackerDialProps {
  tasks: Task[];
  activeTaskId: string;
  onSelectTask: (taskId: string) => void;
  onLogTime: (taskId: string, durationSeconds: number) => void;
  onExpandView?: () => void;
}

export const TimeTrackerDial: React.FC<TimeTrackerDialProps> = ({
  tasks,
  activeTaskId,
  onSelectTask,
  onLogTime,
  onExpandView,
}) => {
  // Initialized at 155 seconds (02:35) matching the spec's iconic readout!
  const [seconds, setSeconds] = useState<number>(155);
  const [isRunning, setIsRunning] = useState<boolean>(false);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (isRunning) {
      interval = setInterval(() => {
        setSeconds((prev) => prev + 1);
      }, 1000);
    } else if (!isRunning && interval) {
      clearInterval(interval);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isRunning]);

  const activeTask = tasks.find((t) => t.id === activeTaskId) || tasks[0];

  const handleToggleTimer = () => {
    if (isRunning) {
      setIsRunning(false);
      if (seconds > 0 && activeTask) {
        onLogTime(activeTask.id, seconds);
      }
    } else {
      setIsRunning(true);
    }
  };

  const handleReset = () => {
    setIsRunning(false);
    setSeconds(0);
  };

  // SVG calculations for radial circle and tick marks
  const size = 230;
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  // Let progress arc represent minutes within the current hour (or 60 min cycle)
  const cycleSeconds = 3600;
  const progressRatio = (seconds % cycleSeconds) / cycleSeconds;
  const strokeDashoffset = circumference - progressRatio * circumference;

  // Generate 60 fine radial tick marks
  const totalTicks = 60;
  const ticks = Array.from({ length: totalTicks }, (_, i) => {
    const angle = (i * 360) / totalTicks;
    const isMajor = i % 5 === 0;
    const tickLength = isMajor ? 8 : 4;
    return {
      id: i,
      angle,
      isMajor,
      tickLength,
    };
  });

  return (
    <div className="bento-card p-6 flex flex-col justify-between relative overflow-hidden bg-white">
      {/* Sunlit subtle glow background */}
      <div className="absolute top-0 right-0 w-48 h-48 bg-radial from-[#FEEDB8]/40 to-transparent pointer-events-none rounded-full blur-2xl" />

      {/* Card Header with ↗ expand button */}
      <div className="flex items-center justify-between mb-3 relative z-10">
        <div>
          <span className="text-[11px] font-stat uppercase tracking-wider text-[#6E6B68] block">
            Focus Dial
          </span>
          <h3 className="text-base font-semibold text-[#1E1E22] tracking-tight">
            Circular Time Tracker
          </h3>
        </div>
        {onExpandView && (
          <button
            onClick={onExpandView}
            className="w-8 h-8 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#1E1E22] flex items-center justify-center transition-colors shadow-xs"
            aria-label="Expand time tracker view"
          >
            <ArrowUpRight className="w-4 h-4 text-[#1E1E22]" />
          </button>
        )}
      </div>

      {/* Task Selector Capsule */}
      <div className="mb-4 relative z-10">
        <label htmlFor="task-select" className="sr-only">
          Select Active Task
        </label>
        <div className="flex items-center gap-2 bg-[#F3EFEA] px-3 py-1.5 rounded-full border border-[#E8E3DC]">
          <Tag className="w-3.5 h-3.5 text-[#F4B33E]" />
          <select
            id="task-select"
            value={activeTaskId}
            onChange={(e) => onSelectTask(e.target.value)}
            className="bg-transparent text-xs font-medium text-[#1E1E22] focus:outline-none w-full truncate cursor-pointer"
          >
            {tasks.map((task) => (
              <option key={task.id} value={task.id}>
                {task.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Radial Meter & Digital Readout */}
      <div className="relative flex items-center justify-center py-2 my-auto">
        <div className="relative w-[230px] h-[230px] flex items-center justify-center">
          {/* Tick Marks SVG */}
          <svg className="absolute inset-0 w-full h-full" viewBox="0 0 230 230">
            <g transform="translate(115, 115)">
              {ticks.map((tick) => (
                <line
                  key={tick.id}
                  x1="0"
                  y1={-radius + 14}
                  x2="0"
                  y2={-radius + 14 + tick.tickLength}
                  stroke={tick.isMajor ? '#6E6B68' : '#E8E3DC'}
                  strokeWidth={tick.isMajor ? 1.5 : 1}
                  transform={`rotate(${tick.angle})`}
                />
              ))}
            </g>
          </svg>

          {/* Background Track Ring */}
          <svg className="absolute inset-0 w-full h-full -rotate-90">
            <circle
              cx="115"
              cy="115"
              r={radius}
              fill="transparent"
              stroke="#F3EFEA"
              strokeWidth={strokeWidth}
            />
            {/* Animated Kinetic Amber Gold Arc */}
            <circle
              cx="115"
              cy="115"
              r={radius}
              fill="transparent"
              stroke="#F4B33E"
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-all duration-300"
            />
          </svg>

          {/* Central Digital Readout (Space Grotesk tabular font) */}
          <div className="text-center z-10">
            <span className="text-[10px] font-stat text-[#6E6B68] uppercase tracking-widest block mb-0.5">
              {isRunning ? 'RECORDING SESSION' : 'PAUSED / READY'}
            </span>
            <div className="font-stat text-4xl sm:text-[42px] font-bold text-[#1E1E22] tracking-tight tabular-nums">
              {formatDuration(seconds)}
            </div>
            <span className="inline-block mt-1 text-[11px] font-medium text-[#6E6B68] bg-[#F3EFEA] px-2.5 py-0.5 rounded-full">
              {activeTask ? activeTask.category.toUpperCase() : 'DEEP WORK'}
            </span>
          </div>
        </div>
      </div>

      {/* Dual Tactile Control Buttons */}
      <div className="flex items-center justify-center gap-3 pt-4 border-t border-[#E8E3DC]/60 relative z-10">
        <button
          onClick={handleToggleTimer}
          className={`flex items-center justify-center gap-2 px-5 py-2.5 rounded-full text-xs font-semibold tracking-tight transition-all duration-200 shadow-sm ${
            isRunning
              ? 'bg-[#1E1E22] text-white hover:bg-[#2E2E34]'
              : 'bg-[#F4B33E] text-[#1E1E22] hover:bg-[#e5a532]'
          }`}
          aria-label={isRunning ? 'Pause time tracker' : 'Start time tracker'}
        >
          {isRunning ? (
            <>
              <Pause className="w-3.5 h-3.5 fill-current" />
              <span>Pause Session</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Start Timer</span>
            </>
          )}
        </button>

        <button
          onClick={handleReset}
          className="w-9 h-9 rounded-full bg-[#F3EFEA] hover:bg-[#ECE7E1] text-[#6E6B68] hover:text-[#1E1E22] flex items-center justify-center transition-colors"
          aria-label="Reset timer to 0"
          title="Reset Timer"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
