"use client";

import React from 'react';
import { UserProfile, Task, DailyWorkload, ScheduleEvent, NavigationTab } from '../../types';
import { HeaderHero } from '../HeaderHero';
import { ProfileVelocityCard } from '../bento/ProfileVelocityCard';
import { TimeTrackerDial } from '../bento/TimeTrackerDial';
import { InvertedFocusModule } from '../bento/InvertedFocusModule';
import { VelocityChartCard } from '../bento/VelocityChartCard';
import { WorkloadBarGaugeCard } from '../bento/WorkloadBarGaugeCard';
import { ProgressRailCard } from '../bento/ProgressRailCard';
import { CalendarTimelineStrip } from '../bento/CalendarTimelineStrip';

interface OverviewScreenProps {
  user: UserProfile;
  tasks: Task[];
  activeTaskId: string;
  onSelectTask: (taskId: string) => void;
  onToggleTask: (taskId: string) => void;
  onLogTime: (taskId: string, durationSeconds: number) => void;
  workloadDays: DailyWorkload[];
  scheduleEvents: ScheduleEvent[];
  onOpenNewTask: () => void;
  onTabChange: (tab: NavigationTab) => void;
}

export const OverviewScreen: React.FC<OverviewScreenProps> = ({
  user,
  tasks,
  activeTaskId,
  onSelectTask,
  onToggleTask,
  onLogTime,
  workloadDays,
  scheduleEvents,
  onOpenNewTask,
  onTabChange,
}) => {
  const completedCount = tasks.filter((t) => t.completed).length;

  return (
    <div className="space-y-6">
      {/* Sunlit Ambient Shimmer Header Hero */}
      <HeaderHero
        user={user}
        onNewTask={onOpenNewTask}
        onViewAnalytics={() => onTabChange('analytics')}
      />

      {/* 12-Column Responsive Bento Grid */}
      <div className="grid grid-cols-1 md:grid-cols-6 lg:grid-cols-12 gap-5 sm:gap-6">
        {/* Module 1: User Profile & Velocity (4 cols) */}
        <div className="md:col-span-3 lg:col-span-4 flex flex-col">
          <ProfileVelocityCard
            user={user}
            completedTasksCount={completedCount}
            totalTasksCount={tasks.length}
            onExpandView={() => onTabChange('team')}
          />
        </div>

        {/* Module 2: Flagship Circular Time Tracker Dial (4 cols) */}
        <div className="md:col-span-3 lg:col-span-4 flex flex-col">
          <TimeTrackerDial
            tasks={tasks}
            activeTaskId={activeTaskId}
            onSelectTask={onSelectTask}
            onLogTime={onLogTime}
            onExpandView={() => onTabChange('time')}
          />
        </div>

        {/* Module 3: Inverted Dark Bento Card Focus Module (4 cols) */}
        <div className="md:col-span-6 lg:col-span-4 flex flex-col">
          <InvertedFocusModule
            tasks={tasks}
            onToggleTask={onToggleTask}
            onExpandView={() => onTabChange('projects')}
          />
        </div>

        {/* Module 4: Velocity Telemetry Smooth Bezier Chart (7 cols) */}
        <div className="md:col-span-6 lg:col-span-7 flex flex-col">
          <VelocityChartCard onExpandView={() => onTabChange('analytics')} />
        </div>

        {/* Module 5: Workload Heatmap Bar Gauges (5 cols) */}
        <div className="md:col-span-6 lg:col-span-5 flex flex-col">
          <WorkloadBarGaugeCard
            workloadDays={workloadDays}
            onExpandView={() => onTabChange('time')}
          />
        </div>

        {/* Module 6: Horizontal Progress Rail (6 cols) */}
        <div className="md:col-span-6 lg:col-span-6 flex flex-col">
          <ProgressRailCard onExpandView={() => onTabChange('analytics')} />
        </div>

        {/* Module 7: Calendar Timeline Strip (6 cols) */}
        <div className="md:col-span-6 lg:col-span-6 flex flex-col">
          <CalendarTimelineStrip
            events={scheduleEvents}
            onAddEvent={onOpenNewTask}
            onExpandView={() => onTabChange('projects')}
          />
        </div>
      </div>
    </div>
  );
};
