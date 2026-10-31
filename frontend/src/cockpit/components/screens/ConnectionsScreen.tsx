"use client";

import React, { useState, useEffect } from 'react';
import { NavigationTab, UserProfile } from '../../types';

interface ClientSite {
  id: string;
  name: string;
  journeyName: string;
  url: string;
  status: 'active' | 'pending';
  lastSeen: string;
  eventsCount: number;
}

export interface ApiKeyRecord {
  apiKey: string;
  journeyName: string;
  description: string;
  createdAt: string;
  isActive: boolean;
  isDev?: boolean;
}

const DEFAULT_SITES: ClientSite[] = [
  {
    id: 'site-1',
    name: 'Main E-Commerce Store',
    journeyName: 'checkout_funnel',
    url: 'https://store.acme.com',
    status: 'active',
    lastSeen: '2 mins ago',
    eventsCount: 4210,
  },
  {
    id: 'site-2',
    name: 'User Onboarding App',
    journeyName: 'user_onboarding',
    url: 'https://app.acme.com/onboarding',
    status: 'active',
    lastSeen: 'Just now',
    eventsCount: 1548,
  },
  {
    id: 'site-3',
    name: 'Self-Serve Help Center',
    journeyName: 'support_portal',
    url: 'https://help.acme.com',
    status: 'active',
    lastSeen: '14 mins ago',
    eventsCount: 890,
  },
  {
    id: 'site-all',
    name: 'Unified Cross-Site Ecosystem',
    journeyName: '*',
    url: 'Multi-domain (*.acme.com)',
    status: 'active',
    lastSeen: 'Live sync',
    eventsCount: 6648,
  },
];

type IntegrationFormat = 'html' | 'react' | 'nextjs' | 'curl';

export interface ConnectionsScreenProps {
  user?: UserProfile | undefined;
  session?: { label?: string; role?: string; journeys?: readonly string[] } | undefined;
  onTabChange?: ((tab: NavigationTab) => void) | undefined;
}

export const ConnectionsScreen: React.FC<ConnectionsScreenProps> = ({
  session,
  onTabChange,
}) => {
  const [sites, setSites] = useState<ClientSite[]>(DEFAULT_SITES);
  const [selectedSiteId, setSelectedSiteId] = useState<string>('site-1');
  const [format, setFormat] = useState<IntegrationFormat>('html');
  const [collectorHost, setCollectorHost] = useState<string>('http://localhost:8000');
  const [apiKey, setApiKey] = useState<string>(
    session?.role ? `cji_live_${session.role}_key` : 'cji_live_2026_operator_key_default'
  );
  const [copied, setCopied] = useState<boolean>(false);
  const [isPinging, setIsPinging] = useState<boolean>(false);
  const [pingResult, setPingResult] = useState<{ ok: boolean; message: string; timestamp?: string } | null>(null);

  // Self-Serve API Keys Management state
  const [apiKeys, setApiKeys] = useState<ApiKeyRecord[]>([]);
  const [isLoadingKeys, setIsLoadingKeys] = useState<boolean>(true);
  const [revealedKeys, setRevealedKeys] = useState<Record<string, boolean>>({});
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [isAddingKey, setIsAddingKey] = useState<boolean>(false);
  const [newKeyDesc, setNewKeyDesc] = useState<string>('');
  const [newKeyJourney, setNewKeyJourney] = useState<string>('*');
  const [isGeneratingKey, setIsGeneratingKey] = useState<boolean>(false);

  // New site modal / inline state
  const [isAddingSite, setIsAddingSite] = useState<boolean>(false);
  const [newSiteName, setNewSiteName] = useState<string>('');
  const [newJourneyName, setNewJourneyName] = useState<string>('');
  const [newSiteUrl, setNewSiteUrl] = useState<string>('');

  const activeSite = sites.find((s) => s.id === selectedSiteId) || sites[0] || DEFAULT_SITES[0]!;

  // Fetch real database keys on mount (self-service for browser users)
  useEffect(() => {
    let isMounted = true;
    async function loadKeys() {
      setIsLoadingKeys(true);
      try {
        const res = await fetch('/api/connections/keys');
        if (res.ok) {
          const data = await res.json();
          if (isMounted && data.keys && Array.isArray(data.keys) && data.keys.length > 0) {
            setApiKeys(data.keys);
            // Default active key to first matched or first live key
            const matchedKey =
              data.keys.find((k: ApiKeyRecord) => k.journeyName === activeSite.journeyName) ||
              data.keys.find((k: ApiKeyRecord) => k.journeyName === '*') ||
              data.keys[0];
            if (matchedKey) {
              setApiKey(matchedKey.apiKey);
            }
          }
        }
      } catch {
        // Fallback gracefully
      } finally {
        if (isMounted) setIsLoadingKeys(false);
      }
    }
    loadKeys();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleAddSite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSiteName.trim() || !newJourneyName.trim()) return;

    const cleanJourney = newJourneyName.trim().toLowerCase().replace(/\s+/g, '_');

    // Automatically provision a dedicated real key for this site via backend API
    try {
      const res = await fetch('/api/connections/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          journeyName: cleanJourney,
          description: `Key for ${newSiteName.trim()}`,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        if (json.key) {
          setApiKeys((prev) => [json.key, ...prev]);
          setApiKey(json.key.apiKey);
        }
      }
    } catch {
      // Non-blocking fallback
    }

    const createdSite: ClientSite = {
      id: `site-${Date.now()}`,
      name: newSiteName.trim(),
      journeyName: cleanJourney,
      url: newSiteUrl.trim() || `https://${cleanJourney}.acme.com`,
      status: 'pending',
      lastSeen: 'Awaiting first event',
      eventsCount: 0,
    };

    setSites((prev) => [...prev, createdSite]);
    setSelectedSiteId(createdSite.id);
    setNewSiteName('');
    setNewJourneyName('');
    setNewSiteUrl('');
    setIsAddingSite(false);
  };

  const handleGenerateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsGeneratingKey(true);
    try {
      const res = await fetch('/api/connections/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          journeyName: newKeyJourney.trim() || '*',
          description: newKeyDesc.trim() || `Key for ${newKeyJourney.trim() || 'all journeys'}`,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        if (json.key) {
          setApiKeys((prev) => [json.key, ...prev]);
          setApiKey(json.key.apiKey);
          setNewKeyDesc('');
          setIsAddingKey(false);
        }
      }
    } catch {
      // Non-blocking fallback
    } finally {
      setIsGeneratingKey(false);
    }
  };

  const handleRevokeKey = async (targetKey: string) => {
    if (!confirm('Are you sure you want to deactivate this API key? Client web apps using this key will immediately be rejected by the collector.')) {
      return;
    }
    try {
      const res = await fetch('/api/connections/keys', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apiKey: targetKey }),
      });
      if (res.ok) {
        setApiKeys((prev) => prev.filter((k) => k.apiKey !== targetKey));
        if (apiKey === targetKey) {
          const next = apiKeys.find((k) => k.apiKey !== targetKey);
          if (next) setApiKey(next.apiKey);
        }
      }
    } catch {
      // Non-blocking fallback
    }
  };

  const toggleRevealKey = (keyString: string) => {
    setRevealedKeys((prev) => ({
      ...prev,
      [keyString]: !prev[keyString],
    }));
  };

  const copySpecificKey = (keyString: string) => {
    navigator.clipboard.writeText(keyString);
    setCopiedKeyId(keyString);
    setTimeout(() => setCopiedKeyId(null), 2000);
  };

  // Generate dynamic snippet based on active site and configuration
  const htmlSnippet = `<!-- CJI Client Telemetry Tracker Embed -->
<script>
window.CJI_CONFIG = {
    api_key: "${apiKey}",
    journey_name: "${activeSite.journeyName}",
    collector_url: "${collectorHost}/collect/batch",
    step_map: {
        "landing_page": "/$",
        "view_item": "/product/.*",
        "cart_view": "/cart",
        "checkout_step": "/checkout",
        "success_step": "/order/success"
    }
};
</script>
<script src="${collectorHost}/tracker.js" defer></script>`;

  const reactHookSnippet = `// hooks/useCJITracker.ts
import { useEffect } from 'react';

export function useCJITracker() {
  useEffect(() => {
    if (typeof window !== 'undefined' && !window.CJI_CONFIG) {
      window.CJI_CONFIG = {
        api_key: '${apiKey}',
        journey_name: '${activeSite.journeyName}',
        collector_url: '${collectorHost}/collect/batch',
        step_map: {
          landing: '/$',
          checkout: '/checkout',
          success: '/success',
        },
      };

      const script = document.createElement('script');
      script.src = '${collectorHost}/tracker.js';
      script.defer = true;
      document.head.appendChild(script);
    }
  }, []);
}`;

  const nextjsSnippet = `// components/CJITrackerScript.tsx (Next.js App Router layout.tsx)
import Script from 'next/script';

export function CJITrackerScript() {
  return (
    <>
      <Script id="cji-tracker-config" strategy="beforeInteractive">
        {\`
          window.CJI_CONFIG = {
            api_key: '${apiKey}',
            journey_name: '${activeSite.journeyName}',
            collector_url: '${collectorHost}/collect/batch'
          };
        \`}
      </Script>
      <Script src="${collectorHost}/tracker.js" strategy="afterInteractive" />
    </>
  );
}`;

  const curlSnippet = `# Send a test batch directly to the CJI Collector API
curl -X POST "${collectorHost}/collect/batch" \\
  -H "Content-Type: application/json" \\
  -H "X-CJI-Key: ${apiKey}" \\
  -d '{
    "api_key": "${apiKey}",
    "events": [
      {
        "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
        "event_id": "manual-ping-'$(date +%s)'",
        "session_id": "sess-test-manual",
        "user_id": "user-test-manual",
        "journey_name": "${activeSite.journeyName}",
        "step_id": "ping_test_step",
        "event_type": "page_view",
        "url": "${activeSite.url || 'https://store.acme.com'}",
        "element_selectors": "body.main",
        "metadata": { "source": "connections_hub_test", "site_id": "${activeSite.id}" }
      }
    ]
  }'`;

  const currentSnippet =
    format === 'html'
      ? htmlSnippet
      : format === 'react'
      ? reactHookSnippet
      : format === 'nextjs'
      ? nextjsSnippet
      : curlSnippet;

  const handleCopy = () => {
    navigator.clipboard.writeText(currentSnippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  const downloadFile = (filename: string, content: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadEmbed = () => {
    downloadFile(`cji-embed-${activeSite.journeyName}.html`, currentSnippet, 'text/html');
  };

  const handleDownloadHook = () => {
    downloadFile(`useCJITracker.ts`, reactHookSnippet, 'text/typescript');
  };

  const handleDownloadTrackerScript = async () => {
    try {
      const res = await fetch(`${collectorHost}/tracker.js`);
      if (res.ok) {
        const text = await res.text();
        downloadFile('tracker.js', text, 'application/javascript');
        return;
      }
    } catch {
      // fallback download template
    }
    downloadFile('tracker.js', `// CJI Tracker Client Script\n// Fetch directly from ${collectorHost}/tracker.js\n`, 'application/javascript');
  };

  const handleSendPing = async () => {
    setIsPinging(true);
    setPingResult(null);
    try {
      const pingEvent = {
        timestamp: new Date().toISOString(),
        event_id: `ping-${Date.now()}`,
        session_id: `test-sess-${Math.random().toString(36).slice(2, 8)}`,
        user_id: `test-user-${Math.random().toString(36).slice(2, 8)}`,
        journey_name: activeSite.journeyName === '*' ? 'checkout_funnel' : activeSite.journeyName,
        step_id: 'connections_ping_test',
        event_type: 'page_view',
        url: activeSite.url || 'http://localhost:3000/connections',
        element_selectors: 'button#test-ping',
        metadata: { client: 'connections_hub', site: activeSite.name },
      };

      const res = await fetch(`${collectorHost}/collect/batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CJI-Key': apiKey,
        },
        body: JSON.stringify({
          api_key: apiKey,
          events: [pingEvent],
        }),
      });

      if (res.ok) {
        setPingResult({
          ok: true,
          message: `Telemetric ping delivered! 1 event verified for '${pingEvent.journey_name}' at port :8000.`,
          timestamp: new Date().toLocaleTimeString(),
        });
      } else {
        const err = await res.json().catch(() => ({}));
        setPingResult({
          ok: false,
          message: `Collector responded with status ${res.status}: ${err.detail || 'Verify collector on :8000 is active.'}`,
        });
      }
    } catch {
      setPingResult({
        ok: false,
        message: `Network failure connecting to ${collectorHost}. Ensure CJI Collector is running (& 'cji-collector' on port 8000).`,
      });
    } finally {
      setIsPinging(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Ambient background glows */}
      <div className="relative">
        <div className="absolute -top-6 -left-6 w-96 h-96 pointer-events-none rounded-full blur-3xl opacity-20 bg-gradient-to-br from-secondary-container via-surface-container-high to-transparent" />
        <div className="absolute top-12 right-12 w-80 h-80 pointer-events-none rounded-full blur-3xl opacity-15 bg-gradient-to-tl from-primary-container to-transparent" />
      </div>

      {/* Hero Bento Header Card */}
      <div className="relative z-10 bg-primary-container text-on-primary rounded-3xl p-6 sm:p-8 shadow-[0_20px_40px_-15px_rgba(15,15,18,0.4)] border border-white/10 flex flex-col lg:flex-row lg:items-center justify-between gap-6 overflow-hidden">
        <div className="space-y-2 max-w-2xl">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-secondary-container animate-pulse" />
            <span className="font-headline-sm text-xs uppercase tracking-wider text-secondary-container font-semibold">
              Telemetry Ingestion Gateway
            </span>
            <span className="font-mono text-[10px] bg-white/10 text-on-primary-container px-2 py-0.5 rounded-full border border-white/10">
              Collector :8000 · Port Active
            </span>
            <span className="font-mono text-[10px] bg-secondary-container/20 text-secondary-container px-2 py-0.5 rounded-full border border-secondary-container/30">
              Self-Serve Credentials
            </span>
          </div>
          <h1 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Client Connections & Multi-Site Ingestion
          </h1>
          <p className="font-body-sm text-sm text-on-primary-container leading-relaxed">
            Integrate client websites and web applications with CJI. Track multiple client properties individually with scoped journey funnels, or aggregate them into an enterprise cross-site customer journey.
          </p>
        </div>

        {/* Quick Stats Badges */}
        <div className="flex items-center gap-3 bg-white/[0.06] backdrop-blur-md p-4 rounded-2xl border border-white/10 shrink-0">
          <div className="text-center px-3 border-r border-white/10">
            <span className="text-xl font-bold font-stat text-white block">{sites.length}</span>
            <span className="text-[10px] uppercase tracking-wider text-on-primary-container">Client Sites</span>
          </div>
          <div className="text-center px-3 border-r border-white/10">
            <span className="text-xl font-bold font-stat text-secondary-container block">100%</span>
            <span className="text-[10px] uppercase tracking-wider text-on-primary-container">Script Reuse</span>
          </div>
          <div className="text-center px-3">
            <span className="text-xl font-bold font-stat text-white block">
              {apiKeys.length > 0 ? apiKeys.length : '1+'}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-on-primary-container">Active Keys</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Multi-Site Switcher & Credentials (Left 5 cols) & Snippet Generator (Right 7 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Client Sites List & API Keys Management (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Sites Bento Card */}
          <div className="bg-surface-container-lowest rounded-3xl p-5 border border-surface-container-high shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-high">
              <div>
                <h2 className="font-title-md text-sm font-bold text-primary">Connected Client Properties</h2>
                <p className="text-xs text-on-surface-variant">Select site to inspect or generate its tailored snippet</p>
              </div>
              <button
                type="button"
                onClick={() => setIsAddingSite(!isAddingSite)}
                className="flex items-center gap-1 text-xs font-semibold px-3 py-1.5 rounded-full bg-secondary-container text-on-secondary-fixed hover:bg-secondary transition-all shadow-xs cursor-pointer"
              >
                <span className="material-symbols-outlined text-[16px]">add</span>
                <span>Connect Site</span>
              </button>
            </div>

            {/* Inline Add Site Form */}
            {isAddingSite && (
              <form onSubmit={handleAddSite} className="p-3.5 bg-surface-container-low rounded-2xl border border-secondary-container/40 space-y-3 animate-in fade-in duration-200">
                <span className="text-xs font-semibold text-primary block">Register New Client Property</span>
                <div>
                  <label className="text-[11px] font-medium text-on-surface-variant block mb-1">
                    Site Display Name
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Marketing Landing Page"
                    value={newSiteName}
                    onChange={(e) => setNewSiteName(e.target.value)}
                    className="w-full bg-surface-container-lowest text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-medium text-on-surface-variant block mb-1">
                    Journey Identifier (<code className="text-secondary font-mono">journey_name</code>)
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. marketing_funnel"
                    value={newJourneyName}
                    onChange={(e) => setNewJourneyName(e.target.value)}
                    className="w-full bg-surface-container-lowest text-xs text-primary font-mono border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-medium text-on-surface-variant block mb-1">
                    Client Website Domain URL
                  </label>
                  <input
                    type="text"
                    placeholder="https://promo.acme.com"
                    value={newSiteUrl}
                    onChange={(e) => setNewSiteUrl(e.target.value)}
                    className="w-full bg-surface-container-lowest text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setIsAddingSite(false)}
                    className="px-3 py-1.5 text-xs text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-1.5 text-xs font-semibold bg-primary-container text-on-primary rounded-full hover:bg-primary transition-all cursor-pointer shadow-xs"
                  >
                    Save & Generate Snippet
                  </button>
                </div>
              </form>
            )}

            {/* Sites List */}
            <div className="space-y-2">
              {sites.map((site) => {
                const isSelected = site.id === selectedSiteId;
                const isAll = site.journeyName === '*';

                return (
                  <button
                    key={site.id}
                    type="button"
                    onClick={() => setSelectedSiteId(site.id)}
                    className={`w-full flex items-center justify-between p-3.5 rounded-2xl border text-left transition-all cursor-pointer group ${
                      isSelected
                        ? 'bg-secondary-container/15 border-secondary-container/60 shadow-xs ring-1 ring-secondary-container/40'
                        : 'bg-surface-container-low hover:bg-surface-container-high/60 border-surface-container-high'
                    }`}
                  >
                    <div className="min-w-0 flex items-start gap-3">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                          isAll
                            ? 'bg-primary-container text-on-primary'
                            : isSelected
                            ? 'bg-secondary-container text-on-secondary-fixed'
                            : 'bg-surface-container-highest text-on-surface-variant'
                        }`}
                      >
                        <span className="material-symbols-outlined text-[18px]">
                          {isAll ? 'hub' : 'language'}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-primary truncate block">
                            {site.name}
                          </span>
                          {isAll && (
                            <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 bg-primary/10 text-primary rounded-full">
                              Unified
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] font-mono text-secondary block truncate">
                          journey: {site.journeyName}
                        </span>
                        <span className="text-[10px] text-on-surface-variant truncate block mt-0.5">
                          {site.url} · {site.eventsCount.toLocaleString()} events
                        </span>
                      </div>
                    </div>

                    <div className="text-right shrink-0">
                      <span className="w-2 h-2 rounded-full inline-block bg-emerald-500" />
                      <span className="text-[10px] text-on-surface-variant block mt-1">
                        {site.lastSeen}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Self-Serve Client API Keys Management Bento Card */}
          <div className="bg-surface-container-lowest rounded-3xl p-5 border border-surface-container-high shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-high">
              <div>
                <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[18px] text-secondary">vpn_key</span>
                  <span>Client API Ingestion Keys</span>
                </h3>
                <p className="text-xs text-on-surface-variant">
                  Cryptographically secure tokens registered in your database
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsAddingKey(!isAddingKey)}
                className="flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-primary transition-all cursor-pointer"
              >
                <span className="material-symbols-outlined text-[14px]">add</span>
                <span>Generate Key</span>
              </button>
            </div>

            {/* Inline Generate Key Form */}
            {isAddingKey && (
              <form onSubmit={handleGenerateKey} className="p-3 bg-surface-container-low rounded-2xl border border-secondary-container/40 space-y-3 animate-in fade-in duration-200">
                <span className="text-xs font-semibold text-primary block">Generate New Ingestion Key</span>
                <div>
                  <label className="text-[11px] font-medium text-on-surface-variant block mb-1">
                    Key Purpose / Description
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Production iOS Webview Key"
                    value={newKeyDesc}
                    onChange={(e) => setNewKeyDesc(e.target.value)}
                    className="w-full bg-surface-container-lowest text-xs text-primary border border-surface-container-high rounded-xl px-3 py-1.5 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-medium text-on-surface-variant block mb-1">
                    Permitted Journey (<code className="text-secondary font-mono">*</code> for all sites)
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="* or specific_journey_name"
                    value={newKeyJourney}
                    onChange={(e) => setNewKeyJourney(e.target.value)}
                    className="w-full bg-surface-container-lowest text-xs text-primary font-mono border border-surface-container-high rounded-xl px-3 py-1.5 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setIsAddingKey(false)}
                    className="px-2.5 py-1 text-xs text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isGeneratingKey}
                    className="px-3.5 py-1.5 text-xs font-semibold bg-primary-container text-on-primary rounded-full hover:bg-primary transition-all cursor-pointer shadow-xs disabled:opacity-50"
                  >
                    {isGeneratingKey ? 'Generating...' : 'Generate & Save Key'}
                  </button>
                </div>
              </form>
            )}

            {/* Active Keys List */}
            <div className="space-y-2">
              {isLoadingKeys ? (
                <div className="py-4 text-center text-xs text-on-surface-variant animate-pulse">
                  Loading active credentials from database...
                </div>
              ) : apiKeys.length === 0 ? (
                <div className="p-3 bg-surface-container-low rounded-xl text-center text-xs text-on-surface-variant">
                  No custom keys yet. Using default session key.
                </div>
              ) : (
                apiKeys.map((record) => {
                  const isCurrentInSnippet = apiKey === record.apiKey;
                  const isRevealed = revealedKeys[record.apiKey];
                  const displayValue = isRevealed
                    ? record.apiKey
                    : `${record.apiKey.slice(0, 9)}••••••••••••••••${record.apiKey.slice(-4)}`;

                  return (
                    <div
                      key={record.apiKey}
                      className={`p-3 rounded-2xl border transition-all ${
                        isCurrentInSnippet
                          ? 'bg-secondary-container/10 border-secondary-container/40 ring-1 ring-secondary-container/30'
                          : 'bg-surface-container-low border-surface-container-high'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-bold text-primary truncate block">
                              {record.description}
                            </span>
                            {isCurrentInSnippet && (
                              <span className="text-[10px] bg-secondary-container text-on-secondary-fixed font-semibold px-2 py-0.5 rounded-full">
                                Active in Snippet
                              </span>
                            )}
                          </div>
                          <span className="text-[11px] font-mono text-secondary block mt-0.5">
                            journey: {record.journeyName}
                          </span>
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            title={isRevealed ? 'Hide Key' : 'Reveal Key'}
                            onClick={() => toggleRevealKey(record.apiKey)}
                            className="p-1 text-on-surface-variant hover:text-primary rounded-lg transition-colors cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-[16px]">
                              {isRevealed ? 'visibility_off' : 'visibility'}
                            </span>
                          </button>
                          <button
                            type="button"
                            title="Copy Key"
                            onClick={() => copySpecificKey(record.apiKey)}
                            className="p-1 text-on-surface-variant hover:text-primary rounded-lg transition-colors cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-[16px]">
                              {copiedKeyId === record.apiKey ? 'check' : 'content_copy'}
                            </span>
                          </button>
                          <button
                            type="button"
                            title="Revoke / Deactivate Key"
                            onClick={() => handleRevokeKey(record.apiKey)}
                            className="p-1 text-on-surface-variant hover:text-error rounded-lg transition-colors cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-[16px]">delete</span>
                          </button>
                        </div>
                      </div>

                      <div className="mt-2 flex items-center justify-between gap-2">
                        <code className="text-[11px] font-mono text-primary bg-surface-container-lowest px-2 py-1 rounded-lg border border-surface-container-high truncate block flex-1">
                          {displayValue}
                        </code>
                        {!isCurrentInSnippet && (
                          <button
                            type="button"
                            onClick={() => setApiKey(record.apiKey)}
                            className="text-[11px] font-semibold text-secondary hover:underline shrink-0 cursor-pointer"
                          >
                            Use in Snippet
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Educational Strategy Bento Card */}
          <div className="bg-surface-container-lowest rounded-3xl p-5 border border-surface-container-high shadow-xs space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-primary">
              <span className="material-symbols-outlined text-[18px] text-secondary">help_outline</span>
              <span>Individual vs. Unified Tracking Strategy</span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              <strong>Individual Tracking:</strong> When client site snippets use distinct <code className="font-mono text-secondary">journey_name</code> values (e.g. <code className="font-mono">checkout_funnel</code> vs <code className="font-mono">support_portal</code>), their dropoff funnels and rage clicks remain totally isolated in your reports.
            </p>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              <strong>Unified Multi-Site Tracking:</strong> Selecting the <code className="font-mono text-primary font-bold">* (All Journeys)</code> filter aggregates every connected site into a single holistic overview without having to change snippet code.
            </p>
          </div>
        </div>

        {/* Right Column: Code Snippet Generator, Tabs & Download Center (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-surface-container-lowest rounded-3xl p-6 border border-surface-container-high shadow-xs space-y-5">
            {/* Active Property Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-surface-container-high">
              <div>
                <span className="font-label-sm text-[11px] uppercase tracking-wider text-secondary font-semibold block">
                  Configuration for Active Selection
                </span>
                <h2 className="font-headline-sm text-lg font-bold text-primary flex items-center gap-2">
                  <span>{activeSite.name}</span>
                  <span className="text-xs font-mono font-normal text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded-full">
                    {activeSite.journeyName}
                  </span>
                </h2>
              </div>

              {onTabChange && (
                <button
                  type="button"
                  onClick={() => onTabChange('analytics')}
                  className="flex items-center gap-1 text-xs font-semibold text-secondary hover:underline cursor-pointer"
                >
                  <span>Open Live Analytics</span>
                  <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                </button>
              )}
            </div>

            {/* Ingestion Parameters Config Row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3.5 bg-surface-container-low rounded-2xl border border-surface-container-high">
              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  Collector Base URL
                </label>
                <input
                  type="text"
                  value={collectorHost}
                  onChange={(e) => setCollectorHost(e.target.value)}
                  className="w-full bg-surface-container-lowest text-xs font-mono text-primary border border-surface-container-high rounded-xl px-2.5 py-1.5 focus:ring-1 focus:ring-secondary outline-none"
                  placeholder="http://localhost:8000"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  CJI API Key (<code className="text-secondary font-mono">X-CJI-Key</code>)
                </label>
                <input
                  type="text"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="w-full bg-surface-container-lowest text-xs font-mono text-primary border border-surface-container-high rounded-xl px-2.5 py-1.5 focus:ring-1 focus:ring-secondary outline-none"
                />
              </div>
            </div>

            {/* Framework Format Tabs */}
            <div className="flex items-center gap-1 border-b border-surface-container-high pb-2">
              {[
                { id: 'html' as IntegrationFormat, label: 'HTML Embed Snippet', icon: 'html' },
                { id: 'react' as IntegrationFormat, label: 'React Hook', icon: 'code' },
                { id: 'nextjs' as IntegrationFormat, label: 'Next.js App Script', icon: 'layers' },
                { id: 'curl' as IntegrationFormat, label: 'cURL / REST API', icon: 'terminal' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setFormat(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                    format === tab.id
                      ? 'bg-primary-container text-on-primary shadow-xs'
                      : 'text-on-surface-variant hover:text-primary hover:bg-surface-container-high'
                  }`}
                >
                  <span className="material-symbols-outlined text-[16px]">{tab.icon}</span>
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            {/* Code Snippet Box */}
            <div className="relative">
              <pre className="p-4 bg-primary-container text-on-primary rounded-2xl text-xs font-mono overflow-x-auto leading-relaxed border border-white/10 max-h-72">
                <code>{currentSnippet}</code>
              </pre>

              {/* Action Toolbar Inside Code Box */}
              <div className="absolute top-3 right-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCopy}
                  className="flex items-center gap-1 bg-white/15 hover:bg-white/25 backdrop-blur-md text-white text-xs font-semibold px-3 py-1.5 rounded-full transition-all border border-white/20 shadow-xs cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[16px]">
                    {copied ? 'check' : 'content_copy'}
                  </span>
                  <span>{copied ? 'Copied!' : 'Copy Code'}</span>
                </button>
              </div>
            </div>

            {/* Download Center Actions */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-2">
                <span className="font-label-sm text-xs font-semibold text-primary">Download Bundle:</span>
                <button
                  type="button"
                  onClick={handleDownloadEmbed}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-primary transition-all cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[16px]">download</span>
                  <span>cji-embed.html</span>
                </button>
                <button
                  type="button"
                  onClick={handleDownloadHook}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-primary transition-all cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[16px]">download</span>
                  <span>useCJITracker.ts</span>
                </button>
              </div>

              <button
                type="button"
                onClick={handleDownloadTrackerScript}
                className="flex items-center gap-1.5 text-xs font-semibold text-secondary hover:underline cursor-pointer"
              >
                <span className="material-symbols-outlined text-[16px]">file_download</span>
                <span>Get Standalone tracker.js</span>
              </button>
            </div>
          </div>

          {/* Live Ingestion Health & Test Ping Card */}
          <div className="bg-surface-container-lowest rounded-3xl p-5 border border-surface-container-high shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px] text-emerald-600">verified</span>
                  <span>Live Telemetry Verification Sandbox</span>
                </h3>
                <p className="text-xs text-on-surface-variant">
                  Fire a test event to verify that the collector endpoint and database ingestion pipeline are active
                </p>
              </div>

              <button
                type="button"
                onClick={handleSendPing}
                disabled={isPinging}
                className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-container text-on-primary hover:bg-primary text-xs font-semibold transition-all shadow-xs disabled:opacity-50 cursor-pointer"
              >
                <span className={`material-symbols-outlined text-[16px] ${isPinging ? 'animate-spin' : ''}`}>
                  {isPinging ? 'sync' : 'send'}
                </span>
                <span>{isPinging ? 'Delivering...' : 'Send Test Ping'}</span>
              </button>
            </div>

            {pingResult && (
              <div
                className={`p-3.5 rounded-2xl text-xs flex items-center gap-2.5 ${
                  pingResult.ok
                    ? 'bg-emerald-500/10 text-emerald-800 border border-emerald-500/30'
                    : 'bg-error-container/20 text-on-error-container border border-error-container'
                }`}
                role="alert"
              >
                <span className="material-symbols-outlined text-[18px] shrink-0">
                  {pingResult.ok ? 'check_circle' : 'error'}
                </span>
                <div className="flex-1">
                  <span className="font-semibold block">{pingResult.message}</span>
                  {pingResult.timestamp && (
                    <span className="text-[10px] opacity-75 font-mono">Timestamp: {pingResult.timestamp}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
