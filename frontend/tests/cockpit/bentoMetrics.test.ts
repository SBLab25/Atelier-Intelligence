import { describe, expect, it } from 'vitest';
import {
  formatDuration,
  formatHoursMinutes,
  calculateProgress,
  computeAllocationPercentages,
  calculateTaskStats,
  findPeakWorkload,
  type TaskItem,
  type WorkloadDay,
} from '@/cockpit/utils/bentoMetrics';

describe('bento metrics utilities', () => {
  it('formatDuration formats mm:ss and hh:mm:ss correctly', () => {
    expect(formatDuration(0)).toBe('00:00');
    expect(formatDuration(155)).toBe('02:35');
    expect(formatDuration(3600)).toBe('01:00:00');
    expect(formatDuration(3665)).toBe('01:01:05');
  });

  it('formatHoursMinutes formats compact hours and minutes', () => {
    expect(formatHoursMinutes(323)).toBe('5h 23m');
    expect(formatHoursMinutes(45)).toBe('45m');
    expect(formatHoursMinutes(120)).toBe('2h 00m');
  });

  it('calculateProgress returns bounded percentage', () => {
    expect(calculateProgress(5, 10)).toBe(50);
    expect(calculateProgress(0, 10)).toBe(0);
    expect(calculateProgress(15, 10)).toBe(100);
    expect(calculateProgress(1, 3)).toBe(33.3);
  });

  it('computeAllocationPercentages accurately calculates proportions', () => {
    const segments = [
      { label: 'Interviews', count: 12, color: '#1E1E22' },
      { label: 'Hired', count: 6, color: '#F4B33E' },
      { label: 'Client Projects', count: 18, color: '#F06A42' },
      { label: 'Internal R&D', count: 4, color: '#E8E3DC' },
    ];
    const computed = computeAllocationPercentages(segments);
    expect(computed.length).toBe(4);
    const totalPercent = computed.reduce((acc: number, s: { percentage: number }) => acc + s.percentage, 0);
    expect(totalPercent).toBeGreaterThanOrEqual(99);
    expect(totalPercent).toBeLessThanOrEqual(101);
  });

  it('calculateTaskStats calculates counts and times', () => {
    const tasks: TaskItem[] = [
      { id: '1', title: 'Task 1', category: 'core', completed: true, estimatedMinutes: 60, spentMinutes: 50, priority: 'high' },
      { id: '2', title: 'Task 2', category: 'review', completed: false, estimatedMinutes: 40, spentMinutes: 10, priority: 'medium' },
      { id: '3', title: 'Task 3', category: 'analytics', completed: true, estimatedMinutes: 90, spentMinutes: 80, priority: 'low' },
    ];
    const stats = calculateTaskStats(tasks);
    expect(stats.total).toBe(3);
    expect(stats.completed).toBe(2);
    expect(stats.pending).toBe(1);
    expect(stats.percentCompleted).toBe(67);
    expect(stats.totalEstimatedMinutes).toBe(190);
    expect(stats.totalSpentMinutes).toBe(140);
  });

  it('findPeakWorkload identifies maximum workload day', () => {
    const days: WorkloadDay[] = [
      { day: 'Mon', hours: 4, minutes: 15, totalMinutes: 255, tasksCount: 6 },
      { day: 'Tue', hours: 6, minutes: 10, totalMinutes: 370, tasksCount: 8 },
      { day: 'Wed', hours: 5, minutes: 23, totalMinutes: 323, tasksCount: 7 },
    ];
    const peak = findPeakWorkload(days);
    expect(peak).not.toBeNull();
    expect(peak?.day).toBe('Tue');
    expect(peak?.totalMinutes).toBe(370);
  });
});
