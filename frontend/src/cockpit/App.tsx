"use client";

/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect } from 'react';
import { NavigationTab, Task, TaskStatus, TaskCategory, TaskPriority, UserProfile, TeamMember, TimeLog } from './types';
import { currentUser as defaultUser, teamMembers, initialTasks, weeklyWorkloadData, scheduleEvents, initialTimeLogs } from './data/mockData';
import { Navbar } from './components/Navbar';
import { LandingPage } from './components/screens/LandingPage';
import { OverviewScreen } from './components/screens/OverviewScreen';
import { AnalyticsScreen } from './components/screens/AnalyticsScreen';
import { TimeOperationsScreen } from './components/screens/TimeOperationsScreen';
import { SquadAndReportsScreen } from './components/screens/SquadAndReportsScreen';
import { ConnectionsScreen } from './components/screens/ConnectionsScreen';
import { SettingsScreen } from './components/screens/SettingsScreen';
import { LoginScreen } from './components/screens/LoginScreen';
import { SignedOutScreen } from './components/screens/SignedOutScreen';
import { NewTaskModal } from './components/modals/NewTaskModal';
import { SearchModal } from './components/modals/SearchModal';
import { SignOutModal } from './components/modals/SignOutModal';

export type AppViewMode = 'landing' | 'app' | 'login' | 'signed-out';

export interface CockpitAppProps {
  initialViewMode?: AppViewMode;
  initialTab?: NavigationTab;
  session?: { label?: string; role?: string; journeys?: readonly string[] };
}

export function CockpitApp({ initialViewMode = 'app', initialTab = 'dashboard', session }: CockpitAppProps) {
  // Default to initialViewMode
  const [viewMode, setViewMode] = useState<AppViewMode>(initialViewMode);
  const [activeTab, setActiveTab] = useState<NavigationTab>(initialTab);

  const userSuffix = session?.label
    ? `_${session.label.toLowerCase().replace(/\s+/g, '_')}`
    : '';

  const isDemoAccount =
    !session?.label ||
    ['system administrator', 'admin', 'elena vance', 'marcus kane', 'priya patel'].includes(
      session.label.toLowerCase().trim()
    );

  const initialUserTasks: Task[] = isDemoAccount
    ? initialTasks
    : [
        {
          id: 'task-onboard-1',
          title: 'Copy client tracking snippet in Connections & install on your website',
          category: 'core',
          priority: 'high',
          status: 'todo',
          completed: false,
          estimatedMinutes: 15,
          spentMinutes: 0,
          assignee: { name: session?.label || 'Account Lead', avatar: '' },
          dueDate: 'Today',
        },
        {
          id: 'task-onboard-2',
          title: 'Verify first live customer telemetry event in Analytics',
          category: 'analytics',
          priority: 'medium',
          status: 'todo',
          completed: false,
          estimatedMinutes: 30,
          spentMinutes: 0,
          assignee: { name: session?.label || 'Account Lead', avatar: '' },
          dueDate: 'Sprint 1',
        },
      ];

  const [tasks, setTasks] = useState<Task[]>(initialUserTasks);
  const [activeTaskId, setActiveTaskId] = useState<string>(() => tasks[0]?.id || 't-1');
  const [timeLogs, setTimeLogs] = useState<TimeLog[]>(isDemoAccount ? initialTimeLogs : []);

  const initialUserMembers: TeamMember[] = isDemoAccount
    ? teamMembers
    : [
        {
          id: 'm-owner',
          name: session?.label || 'Account Owner',
          role: session?.role === 'operator' ? 'Senior Operations Engineer' : 'Journey Intelligence Lead',
          avatar: '',
          status: 'Available',
          hoursLogged: 0,
          capacityHours: 40,
          activeProject: 'Client Ingestion Setup',
        },
      ];

  const [members, setMembers] = useState<TeamMember[]>(initialUserMembers);

  const [user, setUser] = useState<UserProfile>(() => {
    if (session?.label) {
      return {
        ...defaultUser,
        name: session.label,
        role: `${session.role === 'operator' ? 'Senior Operations Engineer' : 'Journey Intelligence Analyst'} · ${session.journeys?.includes('*') ? 'All Journeys' : session.journeys?.join(', ') || 'All Journeys'}`,
        avatar: '',
      };
    }
    return defaultUser;
  });

  const [isHydrated, setIsHydrated] = useState(false);

  // Client-side hydration from localStorage after initial render to eliminate SSR hydration mismatch
  useEffect(() => {
    setIsHydrated(true);

    try {
      const savedTasks = localStorage.getItem(`cji_tasks${userSuffix}`);
      if (savedTasks) {
        const parsed = JSON.parse(savedTasks);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setTasks(parsed);
        }
      }
    } catch (e) {
      console.error('Failed to restore tasks', e);
    }

    try {
      const savedTimeLogs = localStorage.getItem(`cji_time_logs${userSuffix}`);
      if (savedTimeLogs) {
        const parsed = JSON.parse(savedTimeLogs);
        if (Array.isArray(parsed)) {
          setTimeLogs(parsed);
        }
      }
    } catch (e) {
      console.error('Failed to restore time logs', e);
    }

    try {
      const savedMembers = localStorage.getItem(`cji_team_members${userSuffix}`);
      if (savedMembers) {
        const parsed = JSON.parse(savedMembers);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMembers(parsed);
        }
      }
    } catch (e) {
      console.error('Failed to restore team members', e);
    }

    try {
      const storageKey = session?.label
        ? `cji_user_profile_${session.label.toLowerCase().replace(/\s+/g, '_')}`
        : 'cji_user_profile';
      const savedUser = localStorage.getItem(storageKey);
      if (savedUser) {
        const parsed = JSON.parse(savedUser);
        if (!session?.label || parsed.name.toLowerCase() === session.label.toLowerCase()) {
          setUser(parsed);
        }
      }
    } catch (e) {
      console.error('Failed to restore user profile', e);
    }
  }, [userSuffix, session?.label]);

  useEffect(() => {
    if (isHydrated && typeof window !== 'undefined') {
      localStorage.setItem(`cji_tasks${userSuffix}`, JSON.stringify(tasks));
    }
  }, [tasks, userSuffix, isHydrated]);

  useEffect(() => {
    if (isHydrated && typeof window !== 'undefined') {
      localStorage.setItem(`cji_time_logs${userSuffix}`, JSON.stringify(timeLogs));
    }
  }, [timeLogs, userSuffix, isHydrated]);

  useEffect(() => {
    if (isHydrated && typeof window !== 'undefined') {
      localStorage.setItem(`cji_team_members${userSuffix}`, JSON.stringify(members));
    }
  }, [members, userSuffix, isHydrated]);

  useEffect(() => {
    if (isHydrated && typeof window !== 'undefined') {
      const storageKey = session?.label
        ? `cji_user_profile_${session.label.toLowerCase().replace(/\s+/g, '_')}`
        : 'cji_user_profile';
      localStorage.setItem(storageKey, JSON.stringify(user));
    }
  }, [user, session?.label, isHydrated]);

  const [isLoggedIn, setIsLoggedIn] = useState(true);

  // Modals state
  const [isNewTaskOpen, setIsNewTaskOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isSignOutModalOpen, setIsSignOutModalOpen] = useState(false);

  // Global Keyboard Shortcut: ⌘K to open command search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Handlers for authentication & user profile
  const handleLogin = (newUser: UserProfile) => {
    setUser(newUser);
    setIsLoggedIn(true);
    setViewMode('app');
    setActiveTab('analytics');
  };

  const handleConfirmSignOut = async () => {
    setIsSignOutModalOpen(false);
    setIsLoggedIn(false);
    try {
      await fetch('/api/auth/signout', { method: 'POST' });
    } finally {
      window.location.href = '/signed-out';
    }
  };

  const handleUpdateStatus = (newStatus: 'In Focus' | 'Available' | 'In Meeting') => {
    setUser((prev) => ({ ...prev, status: newStatus }));
  };

  const handleUpdateUser = (updatedUser: UserProfile) => {
    setUser(updatedUser);
  };

  // Operational Squad Handlers
  const handleAddMember = (memberData: Omit<TeamMember, 'id'>) => {
    const newMember: TeamMember = {
      id: `m-${Date.now()}`,
      ...memberData,
    };
    setMembers((prev) => [newMember, ...prev]);
  };

  const handleUpdateMemberAvatar = (memberId: string, newAvatar: string) => {
    setMembers((prev) =>
      prev.map((m) => (m.id === memberId ? { ...m, avatar: newAvatar } : m))
    );
  };

  const handleRemoveMember = (memberId: string) => {
    setMembers((prev) => prev.filter((m) => m.id !== memberId));
  };

      // Handlers for task interactions
      const handleToggleTask = (taskId: string) => {
        setTasks((prev) =>
          prev.map((t) => {
            if (t.id === taskId) {
              const nextCompleted = !t.completed;
              return {
                ...t,
                completed: nextCompleted,
                status: nextCompleted ? 'done' : 'in_progress',
              };
            }
            return t;
          })
        );
      };

      const handleUpdateTaskStatus = (taskId: string, status: TaskStatus) => {
        setTasks((prev) =>
          prev.map((t) => {
            if (t.id === taskId) {
              return {
                ...t,
                status,
                completed: status === 'done',
              };
            }
            return t;
          })
        );
      };

      const handleAddTask = (newTaskData: {
        title: string;
        category: TaskCategory;
        priority: TaskPriority;
        estimatedMinutes: number;
        assigneeId: string;
      }) => {
        const fallbackAssignee = members[0] ?? { name: 'Elena Vance', avatar: '' };
        const assigneeMember = members.find((m) => m.id === newTaskData.assigneeId) ?? fallbackAssignee;
        const created: Task = {
          id: `task-${Date.now()}`,
          title: newTaskData.title,
          category: newTaskData.category,
          priority: newTaskData.priority,
          status: 'todo',
          completed: false,
          estimatedMinutes: newTaskData.estimatedMinutes,
          spentMinutes: 0,
          assignee: {
            name: assigneeMember.name,
            avatar: assigneeMember.avatar,
          },
          dueDate: 'Next Sprint',
        };
        setTasks((prev) => [created, ...prev]);
        setActiveTaskId(created.id);
      };

      const handleLogTime = (taskId: string, durationSeconds: number) => {
        const targetTask = tasks.find((t) => t.id === taskId);
        if (!targetTask) return;

        const newLog = {
          id: `log-${Date.now()}`,
          taskId,
          taskTitle: targetTask.title,
          project: 'Aura Bento System',
          durationSeconds,
          timestamp: 'Just now',
          billable: true,
        };

        setTimeLogs((prev) => [newLog, ...prev]);

        // Update spentMinutes on task
        const addedMinutes = Math.round(durationSeconds / 60);
        setTasks((prev) =>
          prev.map((t) =>
            t.id === taskId
              ? { ...t, spentMinutes: t.spentMinutes + addedMinutes }
              : t
          )
        );
      };

      const handleDeleteLog = (logId: string) => {
        setTimeLogs((prev) => prev.filter((l) => l.id !== logId));
      };

      return (
        <div className="min-h-screen bg-background font-body-md text-on-surface flex flex-col selection:bg-secondary-container selection:text-on-secondary-container">
          {/* Show App Navbar whenever in app */}
          {viewMode === 'app' && (
            <Navbar
              activeTab={activeTab}
              onTabChange={(tab) => {
                setViewMode('app');
                setActiveTab(tab);
              }}
              user={user}
              isLoggedIn={isLoggedIn}
              onOpenNewTask={() => setIsNewTaskOpen(true)}
              onOpenSearch={() => setIsSearchOpen(true)}
              onTriggerSignOut={() => setIsSignOutModalOpen(true)}
              onTriggerSignIn={() => {
                window.location.href = '/login';
              }}
              onUpdateStatus={handleUpdateStatus}
              unreadCount={2}
            />
          )}

          {/* Main Content Viewport */}
          <main className="flex-1 w-full bg-background">
            {/* Landing Page View */}
            {viewMode === 'landing' && (
              <LandingPage
                tasks={tasks}
                onToggleTask={handleToggleTask}
                onLaunchCockpit={() => {
                  setViewMode('app');
                  setActiveTab('analytics');
                }}
                onSignIn={() => setViewMode('login')}
                onViewAnalytics={() => {
                  setViewMode('app');
                  setActiveTab('analytics');
                }}
                currentUser={user}
              />
            )}

            {/* Login Screen View */}
            {viewMode === 'login' && (
              <LoginScreen
                onLogin={handleLogin}
                onExploreDemo={() => {
                  setViewMode('app');
                  setActiveTab('analytics');
                }}
              />
            )}

            {/* Signed Out Screen View */}
            {viewMode === 'signed-out' && (
              <SignedOutScreen
                lastUser={user}
                onSignInAgain={() => setViewMode('login')}
                onExploreCockpit={() => {
                  setViewMode('landing');
                }}
              />
            )}

            {/* Normal App Workspace View */}
            {viewMode === 'app' && (
              <>
                {activeTab === 'analytics' && (
                  <AnalyticsScreen
                    tasks={tasks}
                    onNewTask={() => setIsNewTaskOpen(true)}
                  />
                )}

                {(activeTab === 'dashboard' || activeTab === 'overview') && (
                  <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <OverviewScreen
                      user={user}
                      tasks={tasks}
                      activeTaskId={activeTaskId}
                      onSelectTask={setActiveTaskId}
                      onToggleTask={handleToggleTask}
                      onLogTime={handleLogTime}
                      workloadDays={weeklyWorkloadData}
                      scheduleEvents={scheduleEvents}
                      onOpenNewTask={() => setIsNewTaskOpen(true)}
                      onTabChange={setActiveTab}
                    />
                  </div>
                )}

                {activeTab === 'time' && (
                  <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <TimeOperationsScreen
                      tasks={tasks}
                      activeTaskId={activeTaskId}
                      onSelectTask={setActiveTaskId}
                      timeLogs={timeLogs}
                      onLogTime={handleLogTime}
                      onDeleteLog={handleDeleteLog}
                    />
                  </div>
                )}

                {(activeTab === 'reports' || activeTab === 'projects' || activeTab === 'people' || activeTab === 'team') && (
                  <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <SquadAndReportsScreen
                      members={members}
                      onAddMember={handleAddMember}
                      onUpdateMemberAvatar={handleUpdateMemberAvatar}
                      onRemoveMember={handleRemoveMember}
                      onAssignToMember={(_memberId) => {
                        setIsNewTaskOpen(true);
                      }}
                      tasks={tasks}
                      onToggleTask={handleToggleTask}
                      onUpdateTaskStatus={handleUpdateTaskStatus}
                      onNewTask={() => setIsNewTaskOpen(true)}
                    />
                  </div>
                )}

                {activeTab === 'connections' && (
                  <ConnectionsScreen
                    user={user}
                    session={session}
                    onTabChange={setActiveTab}
                  />
                )}

                {activeTab === 'settings' && (
                  <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <SettingsScreen
                      user={user}
                      onUpdateUser={handleUpdateUser}
                      teamMembers={members}
                      onUpdateMemberAvatar={handleUpdateMemberAvatar}
                      isLoggedIn={isLoggedIn}
                      onSignOut={() => setIsSignOutModalOpen(true)}
                      onSwitchViewMode={setViewMode}
                    />
                  </div>
                )}
              </>
            )}
          </main>

          {/* Footer for workspace */}
          {viewMode === 'app' && (
            <footer className="w-full bg-surface-container-low py-space-xl mt-auto border-t border-surface-container-high/60">
              <div className="w-full px-gutter md:px-margin-desktop flex flex-col md:flex-row items-center justify-between gap-space-md">
                <div className="flex items-center gap-space-sm">
                  <div className="w-2 h-2 rounded-full bg-secondary-container"></div>
                  <span className="font-label-md text-label-md text-on-surface-variant">
                    Atelier Intelligence Core
                  </span>
                </div>
                <div className="font-body-sm text-body-sm text-on-surface-variant">
                  © 2025 Atelier Architecture. Tactile Bento Modular System.
                </div>
              </div>
            </footer>
          )}

          {/* Modals */}
          <NewTaskModal
            isOpen={isNewTaskOpen}
            onClose={() => setIsNewTaskOpen(false)}
            onAddTask={handleAddTask}
            teamMembers={members}
          />

          <SearchModal
            isOpen={isSearchOpen}
            onClose={() => setIsSearchOpen(false)}
            tasks={tasks}
            teamMembers={members}
            onSelectTask={setActiveTaskId}
            onTabChange={(tab) => {
              if (tab === 'landing') {
                setViewMode('landing');
              } else {
                setViewMode('app');
                setActiveTab(tab);
              }
            }}
          />

          <SignOutModal
            isOpen={isSignOutModalOpen}
            onClose={() => setIsSignOutModalOpen(false)}
            onConfirmSignOut={handleConfirmSignOut}
            user={user}
          />
        </div>
      );
    }

    export default CockpitApp;

