/**
 * Core pure calculation and transformation logic for Warm Bento Tactile
 */

export interface TaskItem {
  id: string;
  title: string;
  category: 'core' | 'review' | 'analytics' | 'client';
  completed: boolean;
  estimatedMinutes: number;
  spentMinutes: number;
  priority: 'high' | 'medium' | 'low';
}

export interface WorkloadDay {
  day: string;
  hours: number;
  minutes: number;
  totalMinutes: number;
  tasksCount: number;
}

export interface AllocationSegment {
  label: string;
  count: number;
  color: string;
  stripe?: boolean;
}

/**
 * Format total seconds into HH:MM:SS format with tabular zero padding
 */
export function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  
  const pad = (n: number) => n.toString().padStart(2, '0');
  
  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

/**
 * Format hours and minutes into human-readable compact string e.g. "5h 23m"
 */
export function formatHoursMinutes(totalMinutes: number): string {
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m}m`;
  return `${h}h ${m.toString().padStart(2, '0')}m`;
}

/**
 * Calculate progress percentage (0 - 100)
 */
export function calculateProgress(current: number, total: number): number {
  if (total <= 0) return 0;
  const ratio = (current / total) * 100;
  return Math.min(100, Math.max(0, Math.round(ratio * 10) / 10));
}

/**
 * Compute allocation segment percentages so they total exactly 100%
 */
export function computeAllocationPercentages(segments: AllocationSegment[]): { label: string; count: number; percentage: number; color: string; stripe?: boolean }[] {
  const total = segments.reduce((sum, s) => sum + s.count, 0);
  if (total === 0) {
    return segments.map(s => ({ ...s, percentage: 0 }));
  }
  return segments.map(s => ({
    ...s,
    percentage: Math.round((s.count / total) * 100),
  }));
}

/**
 * Calculate task completion stats
 */
export function calculateTaskStats(tasks: TaskItem[]): {
  total: number;
  completed: number;
  pending: number;
  percentCompleted: number;
  totalEstimatedMinutes: number;
  totalSpentMinutes: number;
} {
  const total = tasks.length;
  const completed = tasks.filter(t => t.completed).length;
  const pending = total - completed;
  const percentCompleted = total > 0 ? Math.round((completed / total) * 100) : 0;
  const totalEstimatedMinutes = tasks.reduce((sum, t) => sum + t.estimatedMinutes, 0);
  const totalSpentMinutes = tasks.reduce((sum, t) => sum + t.spentMinutes, 0);

  return {
    total,
    completed,
    pending,
    percentCompleted,
    totalEstimatedMinutes,
    totalSpentMinutes,
  };
}

/**
 * Find peak workload day from array of day records
 */
export function findPeakWorkload(days: WorkloadDay[]): WorkloadDay | null {
  const first = days[0];
  if (!first) return null;
  return days.reduce((peak, cur) => (cur.totalMinutes > peak.totalMinutes ? cur : peak), first);
}
