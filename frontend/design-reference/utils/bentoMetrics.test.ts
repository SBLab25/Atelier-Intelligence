import test from 'node:test';
import assert from 'node:assert/strict';
import {
  formatDuration,
  formatHoursMinutes,
  calculateProgress,
  computeAllocationPercentages,
  calculateTaskStats,
  findPeakWorkload,
  TaskItem,
  WorkloadDay,
} from './bentoMetrics';

test('formatDuration formats mm:ss and hh:mm:ss correctly', () => {
  assert.equal(formatDuration(0), '00:00');
  assert.equal(formatDuration(155), '02:35'); // 2 min 35 sec
  assert.equal(formatDuration(3600), '01:00:00');
  assert.equal(formatDuration(3665), '01:01:05');
});

test('formatHoursMinutes formats compact hours and minutes', () => {
  assert.equal(formatHoursMinutes(323), '5h 23m');
  assert.equal(formatHoursMinutes(45), '45m');
  assert.equal(formatHoursMinutes(120), '2h 00m');
});

test('calculateProgress returns bounded percentage', () => {
  assert.equal(calculateProgress(5, 10), 50);
  assert.equal(calculateProgress(0, 10), 0);
  assert.equal(calculateProgress(15, 10), 100);
  assert.equal(calculateProgress(1, 3), 33.3);
});

test('computeAllocationPercentages accurately calculates proportions', () => {
  const segments = [
    { label: 'Interviews', count: 12, color: '#1E1E22' },
    { label: 'Hired', count: 6, color: '#F4B33E' },
    { label: 'Client Projects', count: 18, color: '#F06A42' },
    { label: 'Internal R&D', count: 4, color: '#E8E3DC' },
  ];
  const computed = computeAllocationPercentages(segments);
  assert.equal(computed.length, 4);
  const totalPercent = computed.reduce((acc, s) => acc + s.percentage, 0);
  assert.ok(totalPercent >= 99 && totalPercent <= 101);
});

test('calculateTaskStats calculates counts and times', () => {
  const tasks: TaskItem[] = [
    { id: '1', title: 'Task 1', category: 'core', completed: true, estimatedMinutes: 60, spentMinutes: 50, priority: 'high' },
    { id: '2', title: 'Task 2', category: 'review', completed: false, estimatedMinutes: 40, spentMinutes: 10, priority: 'medium' },
    { id: '3', title: 'Task 3', category: 'analytics', completed: true, estimatedMinutes: 90, spentMinutes: 80, priority: 'low' },
  ];
  const stats = calculateTaskStats(tasks);
  assert.equal(stats.total, 3);
  assert.equal(stats.completed, 2);
  assert.equal(stats.pending, 1);
  assert.equal(stats.percentCompleted, 67);
  assert.equal(stats.totalEstimatedMinutes, 190);
  assert.equal(stats.totalSpentMinutes, 140);
});

test('findPeakWorkload identifies maximum workload day', () => {
  const days: WorkloadDay[] = [
    { day: 'Mon', hours: 4, minutes: 15, totalMinutes: 255, tasksCount: 6 },
    { day: 'Tue', hours: 6, minutes: 10, totalMinutes: 370, tasksCount: 8 },
    { day: 'Wed', hours: 5, minutes: 23, totalMinutes: 323, tasksCount: 7 },
  ];
  const peak = findPeakWorkload(days);
  assert.ok(peak);
  assert.equal(peak.day, 'Tue');
  assert.equal(peak.totalMinutes, 370);
});
