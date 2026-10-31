/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import { NavigationTab, Task, TaskStatus, TaskCategory, TaskPriority, UserProfile } from './types';
import { currentUser as defaultUser, teamMembers, initialTasks, weeklyWorkloadData, scheduleEvents, initialTimeLogs } from './data/mockData';
import { Navbar } from './components/Navbar';
import { OverviewScreen } from './components/screens/OverviewScreen';
import { AnalyticsScreen } from './components/screens/AnalyticsScreen';
import { TimeOperationsScreen } from './components/screens/TimeOperationsScreen';
import { ProjectsScreen } from './components/screens/ProjectsScreen';
import { TeamScreen } from './components/screens/TeamScreen';
import { LoginScreen } from './components/screens/LoginScreen';
import { SignedOutScreen } from './components/screens/SignedOutScreen';
import { NewTaskModal } from './components/modals/NewTaskModal';
import { SearchModal } from './components/modals/SearchModal';
import { SignOutModal } from './components/modals/SignOutModal';

type AppViewMode = 'app' | 'login' | 'signed-out';

export default function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('analytics');
  const [tasks, setTasks] = useState<Task[]>(initialTasks);
  const [activeTaskId, setActiveTaskId] = useState<string>(initialTasks[0]?.id || 't-1');
  const [timeLogs, setTimeLogs] = useState(initialTimeLogs);
  const [user, setUser] = useState<UserProfile>(defaultUser);
  const [isLoggedIn, setIsLoggedIn] = useState(true);
  const [viewMode, setViewMode] = useState<AppViewMode>('app');

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

  // Handlers for authentication
  const handleLogin = (newUser: UserProfile) => {
    setUser(newUser);
    setIsLoggedIn(true);
    setViewMode('app');
    setActiveTab('analytics');
  };

  const handleConfirmSignOut = () => {
    setIsSignOutModalOpen(false);
    setIsLoggedIn(false);
    setViewMode('signed-out');
  };

  const handleUpdateStatus = (newStatus: 'In Focus' | 'Available' | 'In Meeting') => {
    setUser((prev) => ({ ...prev, status: newStatus }));
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
    const assigneeMember = teamMembers.find((m) => m.id === newTaskData.assigneeId) || teamMembers[0];
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
      {/* Atelier Intelligence Top Navigation Bar */}
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
        onTriggerSignIn={() => setViewMode('login')}
        onUpdateStatus={handleUpdateStatus}
        unreadCount={2}
      />

      {/* Main Content Viewport */}
      <main className="flex-1 w-full bg-background">
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
              setViewMode('app');
              setActiveTab('analytics');
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

            {(activeTab === 'devices' || activeTab === 'time') && (
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

            {(activeTab === 'reports' || activeTab === 'projects') && (
              <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                <ProjectsScreen
                  tasks={tasks}
                  onToggleTask={handleToggleTask}
                  onUpdateStatus={handleUpdateTaskStatus}
                  onNewTask={() => setIsNewTaskOpen(true)}
                />
              </div>
            )}

            {(activeTab === 'people' || activeTab === 'team') && (
              <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                <TeamScreen
                  members={teamMembers}
                  onAssignToMember={() => {
                    setIsNewTaskOpen(true);
                  }}
                />
              </div>
            )}

            {activeTab === 'settings' && (
              <div className="max-w-4xl mx-auto px-4 py-12">
                <div className="bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05)] border border-surface-container-high">
                  <div className="flex items-center justify-between pb-4 border-b border-surface-container-high">
                    <div>
                      <h2 className="font-headline-md text-headline-md text-primary">System & Security Settings</h2>
                      <p className="font-body-sm text-on-surface-variant mt-1">Configure authentication tokens, session timeouts, and workspace roles.</p>
                    </div>
                    {isLoggedIn && (
                      <button
                        onClick={() => setIsSignOutModalOpen(true)}
                        className="bg-tertiary-container hover:bg-tertiary text-on-tertiary px-4 py-2 rounded-full font-label-md text-xs font-semibold transition-all flex items-center gap-1.5"
                      >
                        <span className="material-symbols-outlined text-[16px]">logout</span>
                        <span>Sign Out</span>
                      </button>
                    )}
                  </div>

                  <div className="mt-6 space-y-4">
                    <div className="flex items-center justify-between p-3.5 bg-surface-container-low rounded-xl">
                      <div>
                        <span className="font-title-md text-primary text-sm font-semibold">Active Workstation Token</span>
                        <p className="font-body-sm text-xs text-on-surface-variant">Signed in as {user.name} ({user.role})</p>
                      </div>
                      <span className="bg-secondary-container text-on-secondary-fixed font-label-sm text-xs px-2.5 py-1 rounded-full font-semibold">
                        {user.status}
                      </span>
                    </div>

                    <div className="flex items-center justify-between p-3.5 bg-surface-container-low rounded-xl">
                      <div>
                        <span className="font-title-md text-primary text-sm font-semibold">Authentication Flow Preview</span>
                        <p className="font-body-sm text-xs text-on-surface-variant">Quickly test the standalone login and signed-out screens</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setViewMode('login')}
                          className="bg-primary-container text-on-primary font-label-md text-xs px-3 py-1.5 rounded-full"
                        >
                          View Login Screen
                        </button>
                        <button
                          onClick={() => setViewMode('signed-out')}
                          className="bg-surface-container-high hover:bg-surface-container-highest text-primary font-label-md text-xs px-3 py-1.5 rounded-full"
                        >
                          View Signed Out
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-3.5 bg-surface-container-low rounded-xl">
                      <div>
                        <span className="font-title-md text-primary text-sm font-semibold">Real-time WebSocket Heuristics</span>
                        <p className="font-body-sm text-xs text-on-surface-variant">Stream live user interaction vectors</p>
                      </div>
                      <span className="bg-secondary-container text-on-secondary-fixed font-label-sm text-xs px-2.5 py-1 rounded-full font-semibold">
                        Active
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Atelier Intelligence Footer */}
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

      {/* Modals */}
      <NewTaskModal
        isOpen={isNewTaskOpen}
        onClose={() => setIsNewTaskOpen(false)}
        onAddTask={handleAddTask}
        teamMembers={teamMembers}
      />

      <SearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        tasks={tasks}
        teamMembers={teamMembers}
        onSelectTask={setActiveTaskId}
        onTabChange={(tab) => {
          setViewMode('app');
          setActiveTab(tab);
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
