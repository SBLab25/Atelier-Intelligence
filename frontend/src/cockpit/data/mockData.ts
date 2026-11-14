import { UserProfile, TeamMember, Task, TimeLog, ScheduleEvent, DailyWorkload } from '../types';

export const currentUser: UserProfile = {
  name: 'Elena Vance',
  role: 'Principal Quantitative Strategist',
  avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
  status: 'In Focus',
  weeklyVelocity: 88,
  sprintTarget: 100,
};

export const teamMembers: TeamMember[] = [
  {
    id: 'm1',
    name: 'Elena Vance',
    role: 'Principal Quantitative Strategist',
    avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
    status: 'In Focus',
    hoursLogged: 34.5,
    capacityHours: 40,
    activeProject: 'Bento System Architecture',
  },
  {
    id: 'm2',
    name: 'Marcus Kane',
    role: 'Lead Systems Architect',
    avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80',
    status: 'Deep Coding',
    hoursLogged: 38.2,
    capacityHours: 40,
    activeProject: 'Realtime Telemetry Pipeline',
  },
  {
    id: 'm3',
    name: 'Priya Patel',
    role: 'Staff Product Researcher',
    avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=256&h=256&q=80',
    status: 'Available',
    hoursLogged: 29.0,
    capacityHours: 35,
    activeProject: 'Tactile Ergonomics Audit',
  },
  {
    id: 'm4',
    name: 'Soren Lindqvist',
    role: 'Design Technologist',
    avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=256&h=256&q=80',
    status: 'Reviewing PRs',
    hoursLogged: 31.5,
    capacityHours: 40,
    activeProject: 'Micro-Dial Bezier Curves',
  },
];

export const initialTasks: Task[] = [
  {
    id: 't-1',
    title: 'Audit radial time tracker dial step-angle calculations',
    category: 'core',
    priority: 'high',
    status: 'in_progress',
    completed: false,
    estimatedMinutes: 60,
    spentMinutes: 42,
    assignee: {
      name: 'Elena Vance',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
    },
    dueDate: 'Today, 4:00 PM',
  },
  {
    id: 't-2',
    title: 'Calibrate amber gold progress rail gradient transitions',
    category: 'core',
    priority: 'high',
    status: 'in_progress',
    completed: true,
    estimatedMinutes: 45,
    spentMinutes: 45,
    assignee: {
      name: 'Soren Lindqvist',
      avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=256&h=256&q=80',
    },
    dueDate: 'Today, 2:30 PM',
  },
  {
    id: 't-3',
    title: 'Synthesize quantitative user retention feedback from sprint 41',
    category: 'analytics',
    priority: 'medium',
    status: 'todo',
    completed: false,
    estimatedMinutes: 90,
    spentMinutes: 20,
    assignee: {
      name: 'Priya Patel',
      avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=256&h=256&q=80',
    },
    dueDate: 'Tomorrow, 11:00 AM',
  },
  {
    id: 't-4',
    title: 'Validate ghost perimeter rims on inverted obsidian containers',
    category: 'review',
    priority: 'high',
    status: 'done',
    completed: true,
    estimatedMinutes: 30,
    spentMinutes: 28,
    assignee: {
      name: 'Elena Vance',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
    },
    dueDate: 'Yesterday',
  },
  {
    id: 't-5',
    title: 'Benchmarking Space Grotesk tabular numeral alignment in grid',
    category: 'analytics',
    priority: 'low',
    status: 'done',
    completed: true,
    estimatedMinutes: 40,
    spentMinutes: 35,
    assignee: {
      name: 'Marcus Kane',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80',
    },
    dueDate: 'Yesterday',
  },
  {
    id: 't-6',
    title: 'Deploy zero-pill discipline token hierarchy in Tailwind',
    category: 'core',
    priority: 'medium',
    status: 'todo',
    completed: false,
    estimatedMinutes: 75,
    spentMinutes: 0,
    assignee: {
      name: 'Marcus Kane',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80',
    },
    dueDate: 'Friday',
  },
];

export const weeklyWorkloadData: DailyWorkload[] = [
  { day: 'Mon', date: 'Oct 26', totalMinutes: 255, hoursLabel: '4h 15m', tasksCount: 6 },
  { day: 'Tue', date: 'Oct 27', totalMinutes: 370, hoursLabel: '6h 10m', tasksCount: 9 },
  { day: 'Wed', date: 'Oct 28', totalMinutes: 323, hoursLabel: '5h 23m', isPeak: true, isToday: true, tasksCount: 8 },
  { day: 'Thu', date: 'Oct 29', totalMinutes: 285, hoursLabel: '4h 45m', tasksCount: 7 },
  { day: 'Fri', date: 'Oct 30', totalMinutes: 230, hoursLabel: '3h 50m', tasksCount: 5 },
  { day: 'Sat', date: 'Oct 31', totalMinutes: 70, hoursLabel: '1h 10m', tasksCount: 2 },
  { day: 'Sun', date: 'Nov 01', totalMinutes: 40, hoursLabel: '0h 40m', tasksCount: 1 },
];

export const scheduleEvents: ScheduleEvent[] = [
  {
    id: 'ev-1',
    title: 'Sprint 42 Architecture & Tactical Sync',
    time: '10:00 AM - 10:45 AM',
    duration: '45m',
    category: 'Sprint Governance',
    tagColor: '#F4B33E',
    attendees: [
      { name: 'Elena Vance', avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80' },
      { name: 'Marcus Kane', avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80' },
      { name: 'Soren Lindqvist', avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=256&h=256&q=80' },
    ],
  },
  {
    id: 'ev-2',
    title: 'Micro-Dial Interaction Prototype Walkthrough',
    time: '01:30 PM - 02:15 PM',
    duration: '45m',
    category: 'Design Critique',
    tagColor: '#5E5CE6',
    attendees: [
      { name: 'Soren Lindqvist', avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=256&h=256&q=80' },
      { name: 'Priya Patel', avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=256&h=256&q=80' },
    ],
  },
  {
    id: 'ev-3',
    title: 'Quarterly Quantitative Forecasting Debrief',
    time: '04:00 PM - 05:00 PM',
    duration: '60m',
    category: 'Executive Strategy',
    tagColor: '#F06A42',
    attendees: [
      { name: 'Elena Vance', avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80' },
      { name: 'Priya Patel', avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=256&h=256&q=80' },
      { name: 'Marcus Kane', avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80' },
    ],
  },
];

export const initialTimeLogs: TimeLog[] = [
  {
    id: 'log-1',
    taskId: 't-1',
    taskTitle: 'Audit radial time tracker dial step-angle calculations',
    project: 'Aura Bento System',
    durationSeconds: 2520, // 42 min
    timestamp: 'Today, 09:15 AM',
    billable: true,
  },
  {
    id: 'log-2',
    taskId: 't-2',
    taskTitle: 'Calibrate amber gold progress rail gradient transitions',
    project: 'Warm Tactile Palette',
    durationSeconds: 2700, // 45 min
    timestamp: 'Today, 11:30 AM',
    billable: true,
  },
  {
    id: 'log-3',
    taskId: 't-4',
    taskTitle: 'Validate ghost perimeter rims on inverted obsidian containers',
    project: 'Aura Bento System',
    durationSeconds: 1680, // 28 min
    timestamp: 'Yesterday, 03:45 PM',
    billable: true,
  },
  {
    id: 'log-4',
    taskId: 't-5',
    taskTitle: 'Benchmarking Space Grotesk tabular numeral alignment in grid',
    project: 'Typography Ergonomics',
    durationSeconds: 2100, // 35 min
    timestamp: 'Yesterday, 01:10 PM',
    billable: false,
  },
];
