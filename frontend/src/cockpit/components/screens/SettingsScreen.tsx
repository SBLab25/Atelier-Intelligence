"use client";

import React, { useState, useRef, useEffect } from 'react';
import { UserProfile, TeamMember } from '../../types';

export interface SettingsScreenProps {
  user: UserProfile;
  onUpdateUser: (updatedUser: UserProfile) => void;
  teamMembers?: TeamMember[];
  onUpdateMemberAvatar?: (memberId: string, newAvatar: string) => void;
  isLoggedIn: boolean;
  onSignOut: () => void;
  onSwitchViewMode: (mode: 'landing' | 'login' | 'signed-out') => void;
}

// Preset avatars preserved for Squad onboarding in SquadAndReportsScreen
export const PRESET_AVATARS = [
  {
    id: 'avatar-1',
    label: 'Elena Vance (Principal Strategist)',
    url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
  },
  {
    id: 'avatar-2',
    label: 'Marcus Kane (Lead Architect)',
    url: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80',
  },
  {
    id: 'avatar-3',
    label: 'Priya Patel (UX Research)',
    url: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=256&h=256&q=80',
  },
  {
    id: 'avatar-4',
    label: 'David Miller (Operations Lead)',
    url: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=256&h=256&q=80',
  },
  {
    id: 'avatar-5',
    label: 'Sophia Lin (Data Intelligence)',
    url: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=256&h=256&q=80',
  },
  {
    id: 'avatar-6',
    label: 'Amara Okafor (Systems Engineer)',
    url: 'https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=256&h=256&q=80',
  },
];

export type LLMProviderId = 'anthropic' | 'groq' | 'gemini' | 'openai' | 'mistral' | 'custom';

export interface LLMConfig {
  provider: LLMProviderId;
  apiKey: string;
  model: string;
  baseUrl?: string;
  temperature?: number;
}

export const LLM_PROVIDERS: {
  id: LLMProviderId;
  name: string;
  icon: string;
  placeholderKey: string;
  defaultBaseUrl: string;
  popularModels: string[];
}[] = [
  {
    id: 'anthropic',
    name: 'Anthropic',
    icon: 'smart_toy',
    placeholderKey: 'sk-ant-api03-...',
    defaultBaseUrl: 'https://api.anthropic.com/v1',
    popularModels: ['claude-3-7-sonnet-latest', 'claude-3-5-sonnet-latest', 'claude-3-5-haiku-latest'],
  },
  {
    id: 'groq',
    name: 'Groq',
    icon: 'bolt',
    placeholderKey: 'gsk_...',
    defaultBaseUrl: 'https://api.groq.com/openai/v1',
    popularModels: ['llama-3.3-70b-versatile', 'deepseek-r1-distill-llama-70b', 'mixtral-8x7b-32768', 'llama-3.1-8b-instant'],
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    icon: 'neurology',
    placeholderKey: 'AIzaSy...',
    defaultBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    popularModels: ['gemini-2.0-flash', 'gemini-2.0-flash-thinking-exp', 'gemini-1.5-pro', 'gemini-1.5-flash'],
  },
  {
    id: 'openai',
    name: 'OpenAI',
    icon: 'psychology',
    placeholderKey: 'sk-proj-...',
    defaultBaseUrl: 'https://api.openai.com/v1',
    popularModels: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'o1'],
  },
  {
    id: 'mistral',
    name: 'Mistral AI',
    icon: 'cyclone',
    placeholderKey: '...',
    defaultBaseUrl: 'https://api.mistral.ai/v1',
    popularModels: ['mistral-large-latest', 'codestral-latest', 'pixtral-12b-2409'],
  },
  {
    id: 'custom',
    name: 'Custom / Ollama / Local',
    icon: 'terminal',
    placeholderKey: 'ollama or custom token',
    defaultBaseUrl: 'http://localhost:11434/v1',
    popularModels: ['deepseek-r1', 'llama3.2', 'qwen2.5-coder', 'mistral', 'custom-model'],
  },
];

export const SettingsScreen: React.FC<SettingsScreenProps> = ({
  user,
  onUpdateUser,
  isLoggedIn,
  onSignOut,
  onSwitchViewMode,
}) => {
  // Profile Identity state
  const [name, setName] = useState(user.name);
  const [role, setRole] = useState(user.role);
  const [avatar, setAvatar] = useState(user.avatar);
  const [status, setStatus] = useState(user.status);
  const [avatarUrlInput, setAvatarUrlInput] = useState('');
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // File input ref for operational local photo upload
  const fileInputRef = useRef<HTMLInputElement>(null);

  // LLM / BYOK Configuration state
  const [llmProvider, setLlmProvider] = useState<LLMProviderId>('anthropic');
  const [llmApiKey, setLlmApiKey] = useState<string>('');
  const [llmModel, setLlmModel] = useState<string>('claude-3-7-sonnet-latest');
  const [llmBaseUrl, setLlmBaseUrl] = useState<string>('https://api.anthropic.com/v1');
  const [isKeyVisible, setIsKeyVisible] = useState<boolean>(false);
  const [llmStatus, setLlmStatus] = useState<'idle' | 'saved' | 'cleared'>('idle');
  const [workspaceDataMode, setWorkspaceDataMode] = useState<'clean' | 'demo'>('clean');

  // Load existing LLM configuration from localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      try {
        const savedLlm = localStorage.getItem('cji_llm_config');
        if (savedLlm) {
          const parsed: LLMConfig = JSON.parse(savedLlm);
          if (parsed.provider) setLlmProvider(parsed.provider);
          if (parsed.apiKey) setLlmApiKey(parsed.apiKey);
          if (parsed.model) setLlmModel(parsed.model);
          if (parsed.baseUrl) setLlmBaseUrl(parsed.baseUrl);
          setLlmStatus('saved');
        }
        const savedMode = localStorage.getItem('cji_workspace_data_mode');
        if (savedMode === 'demo' || savedMode === 'clean') {
          setWorkspaceDataMode(savedMode);
        }
      } catch {
        // ignore
      }
    }
  }, []);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.size > 3 * 1024 * 1024) {
        setFeedback('Image file exceeds 3MB limit. Please select a smaller photo.');
        return;
      }
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64 = event.target?.result as string;
        if (base64) {
          setAvatar(base64);
          setFeedback('Photo selected! Click "Save Profile & Avatar Changes" to apply.');
        }
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSaveProfile = (e: React.FormEvent) => {
    e.preventDefault();
    const updated: UserProfile = {
      ...user,
      name: name.trim() || user.name,
      role: role.trim() || user.role,
      avatar: avatar.trim(),
      status,
    };
    onUpdateUser(updated);

    try {
      localStorage.setItem('cji_user_profile', JSON.stringify(updated));
    } catch {
      // ignore
    }

    setFeedback('Profile and avatar updated successfully across the Atelier Workspace.');
    setTimeout(() => setFeedback(null), 3500);
  };

  const handleApplyUrl = () => {
    if (avatarUrlInput.trim()) {
      setAvatar(avatarUrlInput.trim());
      setAvatarUrlInput('');
      setShowUrlInput(false);
      setFeedback('Avatar URL applied. Click "Save Profile & Avatar Changes" to persist.');
    }
  };

  const handleRemoveAvatar = () => {
    setAvatar('');
    setFeedback('Avatar cleared. A monogram initial will be displayed.');
  };

  // Provider change handler: update base URL and default model
  const handleSelectProvider = (provId: LLMProviderId) => {
    setLlmProvider(provId);
    const prov = LLM_PROVIDERS.find((p) => p.id === provId);
    if (prov) {
      setLlmBaseUrl(prov.defaultBaseUrl);
      if (prov.popularModels[0]) {
        setLlmModel(prov.popularModels[0]);
      }
    }
  };

  const handleSaveLLMConfig = (e: React.FormEvent) => {
    e.preventDefault();
    const config: LLMConfig = {
      provider: llmProvider,
      apiKey: llmApiKey.trim(),
      model: llmModel.trim(),
      baseUrl: llmBaseUrl.trim(),
      temperature: 0.2,
    };

    try {
      localStorage.setItem('cji_llm_config', JSON.stringify(config));
    } catch {
      // ignore
    }

    setLlmStatus('saved');
    setFeedback(`LLM API Key & Model configured for ${llmProvider.toUpperCase()} (${llmModel})`);
    setTimeout(() => setFeedback(null), 3500);
  };

  const handleClearLLMConfig = () => {
    setLlmApiKey('');
    try {
      localStorage.removeItem('cji_llm_config');
    } catch {
      // ignore
    }
    setLlmStatus('cleared');
    setFeedback('Custom LLM configuration cleared. System will use default analysis agent.');
    setTimeout(() => setFeedback(null), 3500);
  };

  const handleToggleWorkspaceMode = (mode: 'clean' | 'demo') => {
    setWorkspaceDataMode(mode);
    try {
      localStorage.setItem('cji_workspace_data_mode', mode);
    } catch {
      // ignore
    }
    setFeedback(
      mode === 'clean'
        ? 'Workspace set to Clean Production Ingestion (isolated from demo data).'
        : 'Workspace set to Demo Sandbox Mode (pre-loaded with sample events).'
    );
    setTimeout(() => setFeedback(null), 3500);
  };

  const activeProviderMeta = LLM_PROVIDERS.find((p) => p.id === llmProvider) || LLM_PROVIDERS[0]!;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 animate-fadeIn">
      {/* Header Banner */}
      <div className="bg-primary-container text-on-primary rounded-3xl p-6 sm:p-8 shadow-[0_20px_40px_-15px_rgba(15,15,18,0.4)] border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2.5 h-2.5 rounded-full bg-secondary-container animate-pulse" />
            <span className="font-headline-sm text-xs uppercase tracking-wider text-secondary-container font-semibold">
              Workspace Administration
            </span>
          </div>
          <h1 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Profile & System Settings
          </h1>
          <p className="font-body-sm text-sm text-on-primary-container mt-1">
            Manage your personal profile photo, custom LLM model keys, workspace isolation, and security tokens.
          </p>
        </div>

        {isLoggedIn && (
          <button
            type="button"
            onClick={onSignOut}
            className="self-start sm:self-auto bg-tertiary-container hover:bg-tertiary text-on-tertiary px-5 py-2.5 rounded-full font-label-md text-xs font-semibold transition-all flex items-center gap-2 shadow-xs cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">logout</span>
            <span>Sign Out</span>
          </button>
        )}
      </div>

      {feedback && (
        <div
          className="p-4 bg-emerald-500/10 text-emerald-800 border border-emerald-500/30 rounded-2xl text-xs font-semibold flex items-center gap-2 animate-in fade-in"
          role="status"
        >
          <span className="material-symbols-outlined text-[18px]">check_circle</span>
          <span>{feedback}</span>
        </div>
      )}

      {/* Main Grid: User Profile (Left 6 cols) & LLM Configuration + Security (Right 6 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Client Profile & Avatar Operations (6 cols) */}
        <div className="lg:col-span-6 space-y-6">
          <div className="bg-surface-container-lowest rounded-3xl p-6 sm:p-8 border border-surface-container-high shadow-xs space-y-6">
            <div className="flex items-center justify-between pb-3 border-b border-surface-container-high">
              <div>
                <h2 className="font-title-md text-base font-bold text-primary flex items-center gap-2">
                  <span className="material-symbols-outlined text-[20px] text-secondary">account_circle</span>
                  <span>Client & User Profile Picture</span>
                </h2>
                <p className="text-xs text-on-surface-variant">
                  Update your display photo, role title, and live availability status
                </p>
              </div>
            </div>

            {/* Avatar Preview & Direct Actions */}
            <div className="flex flex-col sm:flex-row items-center gap-6 p-4 bg-surface-container-low rounded-2xl border border-surface-container-high">
              <div className="relative group shrink-0">
                <div className="w-24 h-24 rounded-full overflow-hidden bg-primary-container text-on-primary ring-4 ring-secondary-container/50 shadow-md flex items-center justify-center">
                  {avatar ? (
                    <img src={avatar} alt={name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="font-headline-md text-2xl font-bold uppercase">
                      {name.slice(0, 2) || 'OP'}
                    </span>
                  )}
                </div>

                {/* Upload Overlay Action */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="absolute inset-0 bg-black/50 text-white rounded-full flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer text-[10px] font-semibold"
                  title="Upload New Photo"
                >
                  <span className="material-symbols-outlined text-[20px]">photo_camera</span>
                  <span>Upload</span>
                </button>
              </div>

              {/* Upload & Direct Actions */}
              <div className="space-y-2 text-center sm:text-left flex-1">
                <div className="flex items-center gap-2 justify-center sm:justify-start">
                  <span className="text-sm font-bold text-primary">{name}</span>
                  <span className="text-[10px] font-semibold bg-secondary-container text-on-secondary-fixed px-2 py-0.5 rounded-full">
                    {status}
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant">{role}</p>

                <div className="flex flex-wrap items-center gap-2 pt-1 justify-center sm:justify-start">
                  {/* File Upload Input (Hidden) */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleFileUpload}
                    className="hidden"
                    aria-label="Upload profile image"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary-container text-on-primary hover:bg-primary text-xs font-semibold transition-all shadow-xs cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]">upload_file</span>
                    <span>Upload Image</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setShowUrlInput(!showUrlInput)}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-primary text-xs font-semibold transition-all cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]">link</span>
                    <span>Image URL</span>
                  </button>

                  {avatar && (
                    <button
                      type="button"
                      onClick={handleRemoveAvatar}
                      className="px-2.5 py-1.5 rounded-full text-xs text-error hover:bg-error-container/20 transition-all cursor-pointer"
                      title="Clear custom photo and use monogram"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Optional URL Input Dropdown */}
            {showUrlInput && (
              <div className="p-3 bg-surface-container-low rounded-2xl border border-secondary-container/40 space-y-2 animate-in fade-in duration-150">
                <label className="text-[11px] font-semibold text-primary block">
                  Paste Direct Image URL (HTTPS)
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="url"
                    placeholder="https://example.com/avatar.jpg"
                    value={avatarUrlInput}
                    onChange={(e) => setAvatarUrlInput(e.target.value)}
                    className="flex-1 bg-surface-container-lowest text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary font-mono"
                  />
                  <button
                    type="button"
                    onClick={handleApplyUrl}
                    className="px-3 py-2 text-xs font-semibold bg-primary-container text-on-primary rounded-xl hover:bg-primary cursor-pointer"
                  >
                    Apply
                  </button>
                </div>
              </div>
            )}

            {/* Editable Profile Fields Form */}
            <form onSubmit={handleSaveProfile} className="space-y-4 pt-4 border-t border-surface-container-high">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-primary block mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-primary block mb-1">
                    Job Title / Workspace Role
                  </label>
                  <input
                    type="text"
                    required
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-primary block mb-1">
                  Availability Status
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(['In Focus', 'Available', 'In Meeting'] as const).map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStatus(s)}
                      className={`py-2 px-3 rounded-xl text-xs font-semibold border transition-all cursor-pointer text-center ${
                        status === s
                          ? 'bg-secondary-container text-on-secondary-fixed border-secondary-container shadow-xs'
                          : 'bg-surface-container-low text-on-surface-variant hover:text-primary border-surface-container-high'
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  className="w-full py-3 px-6 rounded-full bg-primary-container hover:bg-primary text-on-primary font-title-md text-xs font-semibold transition-all shadow-md hover:-translate-y-0.5 cursor-pointer flex items-center justify-center gap-2"
                >
                  <span className="material-symbols-outlined text-[18px]">save</span>
                  <span>Save Profile & Avatar Changes</span>
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Right Column: Bring Your Own Key (BYOK) LLM Configuration & System Isolation (6 cols) */}
        <div className="lg:col-span-6 space-y-6">
          {/* Bento Card: Custom LLM Configuration (BYOK) */}
          <div className="bg-surface-container-lowest rounded-3xl p-6 sm:p-8 border border-surface-container-high shadow-xs space-y-6">
            <div className="flex items-center justify-between pb-3 border-b border-surface-container-high">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-title-md text-base font-bold text-primary flex items-center gap-2">
                    <span className="material-symbols-outlined text-[20px] text-secondary">smart_toy</span>
                    <span>Custom LLM & AI Model Integration</span>
                  </h2>
                  {llmApiKey ? (
                    <span className="text-[10px] font-semibold bg-emerald-500/15 text-emerald-800 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                      <span>{llmStatus === 'saved' ? 'Custom Key Verified & Active' : 'Custom Key Active'}</span>
                    </span>
                  ) : (
                    <span className="text-[10px] font-semibold bg-surface-container-high text-on-surface-variant px-2 py-0.5 rounded-full">
                      {llmStatus === 'cleared' ? 'Cleared (System Default)' : 'System Default'}
                    </span>
                  )}
                </div>
                <p className="text-xs text-on-surface-variant mt-0.5">
                  Configure your personal API key and select or write any LLM model for Customer Journey reasoning.
                </p>
              </div>
            </div>

            <form onSubmit={handleSaveLLMConfig} className="space-y-4">
              {/* Provider Selection Tabs */}
              <div>
                <label className="text-xs font-semibold text-primary block mb-1.5">
                  1. Select AI Provider
                </label>
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                  {LLM_PROVIDERS.map((prov) => {
                    const isSelected = llmProvider === prov.id;
                    return (
                      <button
                        key={prov.id}
                        type="button"
                        onClick={() => handleSelectProvider(prov.id)}
                        className={`p-2 rounded-xl text-center border transition-all cursor-pointer flex flex-col items-center gap-1 ${
                          isSelected
                            ? 'bg-secondary-container text-on-secondary-fixed border-secondary-container font-bold shadow-xs'
                            : 'bg-surface-container-low text-on-surface-variant hover:text-primary hover:bg-surface-container-high border-surface-container-high'
                        }`}
                        title={prov.name}
                      >
                        <span className="material-symbols-outlined text-[18px]">{prov.icon}</span>
                        <span className="text-[10px] truncate max-w-full">{prov.name.split(' ')[0]}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Model Choice & Custom Model Input */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-primary block">
                  2. Model Selection (Choose preset or write custom model)
                </label>

                {/* Popular Presets Pills */}
                <div className="flex flex-wrap items-center gap-1.5">
                  {activeProviderMeta.popularModels.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setLlmModel(m)}
                      className={`text-[11px] px-2.5 py-1 rounded-full font-mono transition-all cursor-pointer ${
                        llmModel === m
                          ? 'bg-primary-container text-on-primary font-bold shadow-xs'
                          : 'bg-surface-container-low text-on-surface-variant hover:text-primary hover:bg-surface-container-high'
                      }`}
                    >
                      {m}
                    </button>
                  ))}
                </div>

                {/* Freeform Model Input */}
                <div className="pt-1">
                  <label className="text-[11px] text-on-surface-variant block mb-1">
                    Or write your target model identifier:
                  </label>
                  <input
                    type="text"
                    required
                    value={llmModel}
                    onChange={(e) => setLlmModel(e.target.value)}
                    placeholder="e.g. claude-3-7-sonnet-latest, gpt-4o, llama-3.3-70b-versatile, etc."
                    className="w-full bg-surface-container-low text-xs text-primary font-mono border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
              </div>

              {/* API Key Input */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-primary">
                    3. {activeProviderMeta.name} API Key
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsKeyVisible(!isKeyVisible)}
                    className="text-[11px] text-secondary hover:underline flex items-center gap-1 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[14px]">
                      {isKeyVisible ? 'visibility_off' : 'visibility'}
                    </span>
                    <span>{isKeyVisible ? 'Hide' : 'Reveal'}</span>
                  </button>
                </div>
                <div className="relative">
                  <input
                    type={isKeyVisible ? 'text' : 'password'}
                    value={llmApiKey}
                    onChange={(e) => setLlmApiKey(e.target.value)}
                    placeholder={activeProviderMeta.placeholderKey}
                    className="w-full bg-surface-container-low text-xs text-primary font-mono border border-surface-container-high rounded-xl px-3 py-2 pr-9 outline-none focus:ring-1 focus:ring-secondary"
                  />
                  {llmApiKey && (
                    <span className="absolute right-3 top-2 text-emerald-600 material-symbols-outlined text-[18px]">
                      check_circle
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-on-surface-variant mt-1 block">
                  Stored securely in your client workstation. Keys are never shared across profiles.
                </span>
              </div>

              {/* Optional Custom Base URL */}
              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  Base URL (Optional / Ollama / Proxy)
                </label>
                <input
                  type="url"
                  value={llmBaseUrl}
                  onChange={(e) => setLlmBaseUrl(e.target.value)}
                  placeholder={activeProviderMeta.defaultBaseUrl}
                  className="w-full bg-surface-container-low text-xs text-primary font-mono border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                />
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between gap-3 pt-2 border-t border-surface-container-high">
                {llmApiKey && (
                  <button
                    type="button"
                    onClick={handleClearLLMConfig}
                    className="px-3 py-2 text-xs text-error hover:bg-error-container/20 rounded-xl transition-all cursor-pointer font-semibold"
                  >
                    Clear Key
                  </button>
                )}
                <button
                  type="submit"
                  className="ml-auto px-5 py-2.5 rounded-full bg-primary-container hover:bg-primary text-on-primary font-title-md text-xs font-semibold transition-all shadow-xs cursor-pointer flex items-center gap-1.5"
                >
                  <span className="material-symbols-outlined text-[16px]">key</span>
                  <span>Save LLM Configuration</span>
                </button>
              </div>
            </form>
          </div>

          {/* Bento Card: Workspace Database Isolation & Session Security */}
          <div className="bg-surface-container-lowest rounded-3xl p-6 border border-surface-container-high shadow-xs space-y-4">
            <div className="pb-2 border-b border-surface-container-high">
              <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[18px] text-secondary">database</span>
                <span>Workspace Database & Multi-Tenant Isolation</span>
              </h3>
              <p className="text-xs text-on-surface-variant">
                Control whether this profile inspects isolated live client data or sample sandbox events
              </p>
            </div>

            <div className="space-y-3">
              {/* Isolation Mode Toggle */}
              <div className="p-3.5 bg-surface-container-low rounded-2xl border border-surface-container-high space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-primary">Workspace Ingestion Scope</span>
                  <span
                    className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full ${
                      workspaceDataMode === 'clean'
                        ? 'bg-emerald-500/15 text-emerald-800'
                        : 'bg-secondary-container text-on-secondary-fixed'
                    }`}
                  >
                    {workspaceDataMode === 'clean' ? 'Clean Live Workspace' : 'Demo Sandbox'}
                  </span>
                </div>
                <p className="text-[11px] text-on-surface-variant leading-relaxed">
                  {workspaceDataMode === 'clean'
                    ? 'Isolated live ingestion: queries only show telemetry received with your account API key. No demo data is mixed in.'
                    : 'Sandbox mode: pre-populates sample events and reports for testing and evaluation.'}
                </p>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => handleToggleWorkspaceMode('clean')}
                    className={`flex-1 py-1.5 px-3 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                      workspaceDataMode === 'clean'
                        ? 'bg-primary text-on-primary shadow-xs'
                        : 'bg-surface-container-high text-on-surface-variant hover:text-primary'
                    }`}
                  >
                    Clean Live Workspace
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggleWorkspaceMode('demo')}
                    className={`flex-1 py-1.5 px-3 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                      workspaceDataMode === 'demo'
                        ? 'bg-primary text-on-primary shadow-xs'
                        : 'bg-surface-container-high text-on-surface-variant hover:text-primary'
                    }`}
                  >
                    Demo Sandbox
                  </button>
                </div>
              </div>

              {/* Active Token Details */}
              <div className="p-3 bg-surface-container-low rounded-2xl border border-surface-container-high">
                <span className="text-[11px] font-semibold text-primary block mb-0.5">
                  Authenticated Identity
                </span>
                <span className="text-xs font-mono text-secondary block truncate">
                  {user.name} ({user.role})
                </span>
                <span className="text-[10px] text-on-surface-variant block mt-1">
                  Isolated session secured via TLS 1.3 & Supabase Cryptographic Vault
                </span>
              </div>

              {/* Quick View Modes */}
              <div className="p-3 bg-surface-container-low rounded-2xl border border-surface-container-high space-y-2">
                <span className="text-[11px] font-semibold text-primary block">
                  Quick View Modes (Testing)
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onSwitchViewMode('landing')}
                    className="px-3 py-1.5 text-xs font-semibold rounded-full bg-secondary-container text-on-secondary-fixed hover:bg-secondary transition-all cursor-pointer shadow-xs"
                  >
                    Landing Page
                  </button>
                  <button
                    type="button"
                    onClick={() => onSwitchViewMode('login')}
                    className="px-3 py-1.5 text-xs font-semibold rounded-full bg-primary-container text-on-primary hover:bg-primary transition-all cursor-pointer shadow-xs"
                  >
                    Login Screen
                  </button>
                  <button
                    type="button"
                    onClick={() => onSwitchViewMode('signed-out')}
                    className="px-3 py-1.5 text-xs font-semibold rounded-full bg-surface-container-high hover:bg-surface-container-highest text-primary transition-all cursor-pointer"
                  >
                    Signed Out Screen
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsScreen;
