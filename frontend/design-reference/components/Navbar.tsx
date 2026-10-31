import React, { useState, useRef, useEffect } from 'react';
import { NavigationTab, UserProfile } from '../types';

interface NavbarProps {
  activeTab: NavigationTab;
  onTabChange: (tab: NavigationTab) => void;
  user: UserProfile;
  isLoggedIn: boolean;
  onOpenNewTask: () => void;
  onOpenSearch: () => void;
  onTriggerSignOut: () => void;
  onTriggerSignIn: () => void;
  onUpdateStatus?: (status: 'In Focus' | 'Available' | 'In Meeting') => void;
  unreadCount?: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  user,
  isLoggedIn,
  onOpenNewTask,
  onOpenSearch,
  onTriggerSignOut,
  onTriggerSignIn,
  onUpdateStatus,
  unreadCount = 2,
}) => {
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const navItems: { id: NavigationTab; label: string }[] = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'people', label: 'People' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'devices', label: 'Devices' },
    { id: 'reports', label: 'Reports' },
    { id: 'settings', label: 'Settings' },
  ];

  const currentTab =
    activeTab === 'overview'
      ? 'dashboard'
      : activeTab === 'time'
      ? 'devices'
      : activeTab === 'team'
      ? 'people'
      : activeTab === 'projects'
      ? 'reports'
      : activeTab;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="sticky top-0 left-0 right-0 z-50 bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.04)] border-b border-surface-container-high/60">
      <div className="h-20 w-full px-gutter md:px-margin-desktop flex items-center justify-between gap-space-lg">
        {/* Brand */}
        <div className="flex items-center gap-space-md flex-shrink-0">
          <button
            onClick={() => onTabChange('analytics')}
            className="flex items-center gap-space-sm bg-surface-container-lowest px-space-md py-space-sm rounded-full shadow-[0_1px_2px_rgba(40,30,20,0.04)] hover:shadow transition-all group"
            aria-label="Atelier Intelligence Home"
          >
            <div className="w-2.5 h-2.5 rounded-full bg-secondary-container animate-pulse"></div>
            <span className="font-headline-sm text-headline-sm tracking-tight text-primary">
              Atelier Intelligence
            </span>
            <span className="font-label-sm text-label-sm uppercase bg-surface-container-high text-on-surface-variant px-space-xs py-0.5 rounded-full">
              v2.4
            </span>
          </button>
        </div>

        {/* Center Navigation Tabs */}
        <div className="hidden lg:flex items-center gap-space-md">
          <div className="flex items-center bg-surface-container-lowest p-1.5 rounded-full shadow-[0_1px_2px_rgba(40,30,20,0.04)]">
            <nav className="flex items-center gap-1" aria-label="Desktop Navigation">
              {navItems.map((item) => {
                const isActive = currentTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onTabChange(item.id)}
                    className={`font-title-md text-title-md rounded-full px-space-lg py-2 transition-all duration-200 ${
                      isActive
                        ? 'bg-primary text-on-primary shadow-sm font-semibold'
                        : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low'
                    }`}
                    aria-current={isActive ? 'page' : undefined}
                    type="button"
                  >
                    {item.label}
                  </button>
                );
              })}
            </nav>
          </div>
        </div>

        {/* Right Actions: Search, Notifications, Quick Add, User Avatar & Menu */}
        <div className="flex items-center gap-space-sm flex-shrink-0">
          {/* Search Button */}
          <button
            onClick={onOpenSearch}
            aria-label="Search"
            className="w-10 h-10 rounded-full bg-surface-container-lowest flex items-center justify-center text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors shadow-[0_1px_2px_rgba(40,30,20,0.04)]"
            type="button"
          >
            <span className="material-symbols-outlined text-[20px]">search</span>
          </button>

          {/* Notifications Button */}
          <button
            onClick={onOpenSearch}
            aria-label="Notifications"
            className="relative w-10 h-10 rounded-full bg-surface-container-lowest flex items-center justify-center text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors shadow-[0_1px_2px_rgba(40,30,20,0.04)]"
            type="button"
          >
            <span className="material-symbols-outlined text-[20px]">notifications</span>
            {unreadCount > 0 && (
              <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-secondary-container"></span>
            )}
          </button>

          {/* Quick Add Button */}
          <button
            onClick={onOpenNewTask}
            aria-label="Quick Add"
            className="w-10 h-10 rounded-full bg-surface-container-lowest flex items-center justify-center text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors shadow-[0_1px_2px_rgba(40,30,20,0.04)]"
            type="button"
          >
            <span className="material-symbols-outlined text-[20px]">add</span>
          </button>

          {/* User Profile Avatar Capsule or Sign In Button */}
          {isLoggedIn ? (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                className="relative flex items-center justify-center p-0.5 rounded-full bg-secondary-container/40 hover:ring-2 hover:ring-secondary transition-all cursor-pointer"
                aria-label="Toggle user profile menu"
                aria-expanded={isUserMenuOpen}
              >
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center overflow-hidden">
                  {user.avatar ? (
                    <img src={user.avatar} alt={user.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="material-symbols-outlined text-on-primary text-[18px]">person</span>
                  )}
                </div>
              </button>

              {/* Tactile Profile Dropdown Menu */}
              {isUserMenuOpen && (
                <div className="absolute right-0 mt-3 w-64 bg-surface-container-lowest rounded-2xl p-3 shadow-[0_16px_36px_-12px_rgba(0,0,0,0.25)] border border-surface-container-high z-50 animate-in fade-in zoom-in-95 duration-150">
                  {/* User Info */}
                  <div className="p-2 border-b border-surface-container-high mb-2">
                    <div className="flex items-center gap-2.5">
                      <img
                        src={user.avatar}
                        alt={user.name}
                        className="w-9 h-9 rounded-full object-cover ring-1 ring-surface-container-high"
                      />
                      <div className="min-w-0">
                        <span className="text-xs font-bold text-primary block leading-tight truncate">
                          {user.name}
                        </span>
                        <span className="text-[10px] text-on-surface-variant truncate block">
                          {user.role}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Status Picker */}
                  <div className="px-2 py-1 mb-2">
                    <span className="font-label-sm text-[10px] uppercase text-on-surface-variant block mb-1">
                      Current Telemetry State
                    </span>
                    <div className="flex items-center gap-1 bg-surface-container-low p-1 rounded-xl">
                      {(['In Focus', 'Available', 'In Meeting'] as const).map((st) => (
                        <button
                          key={st}
                          type="button"
                          onClick={() => {
                            if (onUpdateStatus) onUpdateStatus(st);
                          }}
                          className={`text-[10px] font-medium px-2 py-1 rounded-lg flex-1 transition-all ${
                            user.status === st
                              ? 'bg-primary-container text-on-primary font-semibold'
                              : 'text-on-surface-variant hover:text-on-surface'
                          }`}
                        >
                          {st.split(' ')[0]}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="space-y-1 pt-1 border-t border-surface-container-high">
                    <button
                      type="button"
                      onClick={() => {
                        setIsUserMenuOpen(false);
                        onTabChange('settings');
                      }}
                      className="w-full flex items-center gap-2 p-2 rounded-xl text-xs font-medium text-primary hover:bg-surface-container-low transition-colors text-left"
                    >
                      <span className="material-symbols-outlined text-[16px] text-on-surface-variant">settings</span>
                      <span>Account Settings</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setIsUserMenuOpen(false);
                        onTriggerSignOut();
                      }}
                      className="w-full flex items-center justify-between p-2 rounded-xl text-xs font-semibold text-tertiary-container hover:bg-error-container/30 transition-colors text-left group"
                    >
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-[16px] text-tertiary-container">logout</span>
                        <span>Sign Out of Atelier</span>
                      </div>
                      <span className="material-symbols-outlined text-[14px] opacity-0 group-hover:opacity-100 transition-opacity">
                        arrow_forward
                      </span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <button
              onClick={onTriggerSignIn}
              className="bg-primary-container hover:bg-primary text-on-primary font-title-md text-xs px-4 py-2 rounded-full font-semibold shadow-sm transition-all hover:-translate-y-0.5 flex items-center gap-1.5"
            >
              <span className="material-symbols-outlined text-[16px]">login</span>
              <span>Sign In</span>
            </button>
          )}
        </div>
      </div>

      {/* Mobile Horizontal Navigation Tabs */}
      <div className="lg:hidden flex items-center overflow-x-auto px-4 py-2 bg-surface-container-lowest border-t border-surface-container-high gap-1">
        {navItems.map((item) => {
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`font-title-md text-xs whitespace-nowrap rounded-full px-3 py-1.5 transition-all ${
                isActive
                  ? 'bg-primary text-on-primary shadow-sm font-semibold'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </header>
  );
};
