(function () {
    'use strict';

    if (typeof window === 'undefined') {
        return;
    }

    if (!window.CJI_CONFIG) {
        console.warn("CJITracker: window.CJI_CONFIG not configured. Telemetry is dormant.");
        return;
    }

    const CONFIG = window.CJI_CONFIG;
    const ENDPOINT = CONFIG.collector_url || "http://localhost:8000/collect/batch";
    const API_KEY = CONFIG.api_key;
    const JOURNEY_NAME = CONFIG.journey_name || "unknown_journey";
    const STEP_MAP = CONFIG.step_map || {};
    
    const BATCH_SIZE = CONFIG.batch_size || 20;
    const FLUSH_INTERVAL = CONFIG.flush_interval || 5000;
    const MAX_OFFLINE_QUEUE = 250;
    const STORAGE_KEY = 'cji_offline_events_v1';

    let eventQueue = [];
    let flushTimer = null;
    let isFlushing = false;
    let stepEnteredAt = Date.now();
    let currentStepId = '';
    let lastRageClickTime = 0;

    // --- ID Generation ---
    function genId() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0;
            var v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    // --- User & Session Identity ---
    let userId = '';
    try {
        userId = localStorage.getItem('cji_user_id') || '';
        if (!userId) {
            userId = genId();
            localStorage.setItem('cji_user_id', userId);
        }
    } catch {
        userId = genId();
    }

    // Session is per-tab
    const sessionId = genId();

    // --- Offline Storage Helpers ---
    function loadOfflineEvents() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) {
                    eventQueue = [...parsed.slice(-MAX_OFFLINE_QUEUE), ...eventQueue];
                }
            }
        } catch {
            // Ignore storage read errors
        }
    }

    function saveOfflineEvents() {
        try {
            if (eventQueue.length === 0) {
                localStorage.removeItem(STORAGE_KEY);
            } else {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(eventQueue.slice(-MAX_OFFLINE_QUEUE)));
            }
        } catch {
            // Storage quota exceeded or disabled
        }
    }

    // --- Helpers ---
    function sanitiseUrl(urlStr) {
        try {
            const url = new URL(urlStr);
            return url.origin + url.pathname;
        } catch {
            return String(urlStr).split('?')[0].split('#')[0];
        }
    }

    function getStepId(path) {
        for (const [stepName, regexStr] of Object.entries(STEP_MAP)) {
            try {
                if (new RegExp(regexStr).test(path)) {
                    return stepName;
                }
            } catch {}
        }
        let cleanPath = path.replace(/\/$/, "");
        return cleanPath ? cleanPath.substring(cleanPath.lastIndexOf('/') + 1) : "landing_page";
    }

    currentStepId = getStepId(window.location.pathname);

    function getElementSelector(el) {
        if (!el || el.nodeType !== 1) return "";
        let selector = el.tagName.toLowerCase();
        if (el.id) {
            selector += "#" + el.id;
        } else if (el.className && typeof el.className === "string") {
            const cleanClasses = el.className.trim().split(/\s+/).slice(0, 3).join('.');
            if (cleanClasses) selector += "." + cleanClasses;
        }
        return selector.slice(0, 512);
    }

    function getDwellMs() {
        return Math.max(0, Date.now() - stepEnteredAt);
    }

    // --- Core Analytics ---
    function makeEvent(type, metadata = {}, targetElement = null) {
        const dwell = getDwellMs();
        const baseMetadata = {
            ...metadata,
            duration_ms: dwell,
            online: navigator.onLine !== false
        };

        return {
            timestamp: new Date().toISOString(),
            event_id: genId(),
            session_id: sessionId,
            user_id: userId,
            journey_name: JOURNEY_NAME,
            step_id: currentStepId,
            event_type: type,
            url: sanitiseUrl(window.location.href),
            element_selectors: targetElement ? getElementSelector(targetElement) : null,
            metadata: baseMetadata
        };
    }

    function flush() {
        if (eventQueue.length === 0 || isFlushing) return;

        // Offline check
        if (typeof navigator !== 'undefined' && navigator.onLine === false) {
            saveOfflineEvents();
            return;
        }

        isFlushing = true;
        const currentBatch = [...eventQueue];
        eventQueue = [];

        const payload = JSON.stringify({
            api_key: API_KEY,
            events: currentBatch
        });

        // Use sendBeacon for unload/abandon events
        const isAbandon = currentBatch.some(e => e.event_type === 'abandon');
        if (typeof navigator !== 'undefined' && navigator.sendBeacon && isAbandon) {
            try {
                const blob = new Blob([payload], { type: 'application/json' });
                const ok = navigator.sendBeacon(ENDPOINT, blob);
                if (ok) {
                    saveOfflineEvents();
                    isFlushing = false;
                    return;
                }
            } catch {
                // Fall through to fetch
            }
        }

        fetch(ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CJI-Key': API_KEY || ''
            },
            body: payload,
            keepalive: true
        })
            .then(res => {
                if (res.ok) {
                    saveOfflineEvents();
                } else if (res.status >= 500 || res.status === 429) {
                    // Retryable server failure: re-enqueue un-sent events
                    eventQueue = [...currentBatch, ...eventQueue].slice(-MAX_OFFLINE_QUEUE);
                    saveOfflineEvents();
                }
            })
            .catch(() => {
                // Network unreachable: buffer back to offline storage
                eventQueue = [...currentBatch, ...eventQueue].slice(-MAX_OFFLINE_QUEUE);
                saveOfflineEvents();
            })
            .finally(() => {
                isFlushing = false;
            });
    }

    function push(event) {
        eventQueue.push(event);
        saveOfflineEvents();

        if (eventQueue.length >= BATCH_SIZE) {
            flush();
        } else if (!flushTimer) {
            flushTimer = setTimeout(() => {
                flush();
                flushTimer = null;
            }, FLUSH_INTERVAL);
        }
    }

    // --- Auto Rage-Click Detection ---
    let clickHistory = [];
    document.addEventListener("click", (e) => {
        const now = Date.now();
        const target = e.target;
        push(makeEvent("click", { click_x: e.clientX, click_y: e.clientY }, target));

        clickHistory.push({ time: now, el: target, x: e.clientX, y: e.clientY });
        // Retain only clicks within 500ms
        clickHistory = clickHistory.filter(c => now - c.time <= 500);

        // Check if 3+ clicks occur in close proximity (<=24px) or on the same interactive element
        const interactiveTarget = target.closest ? target.closest('button, a, input, select, textarea, [role="button"], form') : target;
        const matchingClicks = clickHistory.filter(c => {
            if (c.el === target) return true;
            if (interactiveTarget && c.el.closest && c.el.closest('button, a, input, select, textarea, [role="button"], form') === interactiveTarget) return true;
            const dx = c.x - e.clientX;
            const dy = c.y - e.clientY;
            return (dx * dx + dy * dy) <= 576; // 24px radius
        });

        if (matchingClicks.length >= 3 && now - lastRageClickTime > 1500) {
            lastRageClickTime = now;
            push(makeEvent("rage_click", {
                reason: "repeated_rapid_clicks",
                click_count: matchingClicks.length,
                click_x: e.clientX,
                click_y: e.clientY,
                target_selector: getElementSelector(interactiveTarget || target)
            }, target));
            clickHistory = [];
        }
    }, true);

    // --- Form Submits ---
    document.addEventListener("submit", (e) => {
        const form = e.target;
        push(makeEvent("form_submit", {
            form_id: form.id || "unknown_form",
            action: form.action || window.location.pathname
        }, form));
    }, true);

    // --- Automatic Error & Promise Capture ---
    window.addEventListener("error", (e) => {
        push(makeEvent("error", {
            message: String(e.message || "Unknown error").slice(0, 500),
            filename: e.filename || "",
            lineno: e.lineno || 0,
            colno: e.colno || 0,
            stack: e.error && e.error.stack ? String(e.error.stack).slice(0, 800) : null
        }));
    });

    window.addEventListener("unhandledrejection", (e) => {
        const reason = e.reason;
        push(makeEvent("error", {
            code: "PROMISE_REJECTION",
            reason: reason ? String(reason.message || reason).slice(0, 500) : "Unhandled rejection"
        }));
    });

    // --- Navigation & Dwell Tracking ---
    function onStepTransition(newPath) {
        const nextStep = getStepId(newPath);
        if (nextStep !== currentStepId) {
            push(makeEvent("step_complete", {
                completed_step: currentStepId,
                next_step: nextStep,
                dwell_ms: getDwellMs()
            }));
            currentStepId = nextStep;
            stepEnteredAt = Date.now();
            setTimeout(() => {
                push(makeEvent("page_view", { title: document.title, step_id: currentStepId }));
            }, 50);
        }
    }

    // Wrap History API for SPA Navigation
    function wrapHistory(type) {
        const orig = history[type];
        return function () {
            const rv = orig.apply(this, arguments);
            const e = new Event('cji_' + type);
            window.dispatchEvent(e);
            return rv;
        };
    }
    history.pushState = wrapHistory('pushState');
    history.replaceState = wrapHistory('replaceState');

    window.addEventListener('cji_pushState', () => onStepTransition(window.location.pathname));
    window.addEventListener('cji_replaceState', () => onStepTransition(window.location.pathname));
    window.addEventListener('popstate', () => onStepTransition(window.location.pathname));

    // Page Load & Initial Page View
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        push(makeEvent("page_view", { title: document.title, initial: true }));
    } else {
        document.addEventListener("DOMContentLoaded", () => {
            push(makeEvent("page_view", { title: document.title, initial: true }));
        });
    }

    // Page Exit & Abandonment
    window.addEventListener("beforeunload", () => {
        push(makeEvent("abandon", {
            time_on_page: "tracked",
            dwell_ms: getDwellMs()
        }));
        flush();
    });

    // Auto-drain offline queue when returning online
    window.addEventListener("online", () => {
        flush();
    });

    // Initialize: load offline events
    loadOfflineEvents();
    if (navigator.onLine !== false && eventQueue.length > 0) {
        flush();
    }

    // Periodic Heartbeat (keepalive every 60s of active session)
    setInterval(() => {
        if (!document.hidden && navigator.onLine !== false) {
            push(makeEvent("identify", {
                heartbeat: true,
                active_step: currentStepId,
                total_session_dwell_ms: getDwellMs()
            }));
        }
    }, 60000);

    // --- Official Public API ---
    window.CJITracker = {
        track: function(type, metadata = {}, targetElement = null) {
            push(makeEvent(type, metadata, targetElement));
        },
        trackStep: function(stepName) {
            currentStepId = stepName;
            stepEnteredAt = Date.now();
            push(makeEvent("step_complete", { custom_step: stepName }));
        },
        identify: function(newUserId, traits = {}) {
            if (newUserId) {
                userId = String(newUserId);
                try {
                    localStorage.setItem('cji_user_id', userId);
                } catch {}
            }
            push(makeEvent("identify", { traits }));
        },
        flush: function() {
            flush();
        },
        getSessionId: function() {
            return sessionId;
        },
        getUserId: function() {
            return userId;
        },
        getCurrentStep: function() {
            return currentStepId;
        },
        getDwellMs: function() {
            return getDwellMs();
        },
        getQueueLength: function() {
            return eventQueue.length;
        }
    };

})();
