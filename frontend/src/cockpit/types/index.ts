export type NavigationTab = 'landing' | 'dashboard' | 'people' | 'analytics' | 'devices' | 'reports' | 'connections' | 'settings' | 'overview' | 'time' | 'projects' | 'team';

export type TaskPriority = 'high' | 'medium' | 'low';
export type TaskCategory = 'core' | 'review' | 'analytics' | 'client';
export type TaskStatus = 'todo' | 'in_progress' | 'review' | 'done';

export interface UserProfile {
  name: string;
  role: string;
  avatar: string;
  status: 'In Focus' | 'Available' | 'In Meeting';
  weeklyVelocity: number;
  sprintTarget: number;
}

export interface TeamMember {
  id: string;
  name: string;
  role: string;
  avatar: string;
  status: string;
  hoursLogged: number;
  capacityHours: number;
  activeProject: string;
}

export interface Task {
  id: string;
  title: string;
  category: TaskCategory;
  priority: TaskPriority;
  status: TaskStatus;
  completed: boolean;
  estimatedMinutes: number;
  spentMinutes: number;
  assignee: {
    name: string;
    avatar: string;
  };
  dueDate: string;
}

export interface TimeLog {
  id: string;
  taskId: string;
  taskTitle: string;
  project: string;
  durationSeconds: number;
  timestamp: string;
  billable: boolean;
}

export interface ScheduleEvent {
  id: string;
  title: string;
  time: string;
  duration: string;
  category: string;
  tagColor: string;
  attendees: { name: string; avatar: string }[];
}

export interface DailyWorkload {
  day: string;
  date: string;
  isToday?: boolean;
  totalMinutes: number;
  hoursLabel: string;
  isPeak?: boolean;
  tasksCount: number;
}
