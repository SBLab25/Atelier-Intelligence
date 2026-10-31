(function () {
    'use strict';

    if (typeof window === 'undefined' || !window.CJI_CONFIG) {
        console.warn("CJITracker: CJI_CONFIG not found, exiting.");
        return;
    }

    const CONFIG = window.CJI_CONFIG;
    const ENDPOINT = CONFIG.collector_url || "http://localhost:8000/collect/batch";
    const API_KEY = CONFIG.api_key;
    const JOURNEY_NAME = CONFIG.journey_name || "unknown_journey";
    const STEP_MAP = CONFIG.step_map || {};
    
    const BATCH_SIZE = 20;
    const FLUSH_INTERVAL = 5000;

    let eventQueue = [];
    let flushTimer = null;

    // --- Identity ---
    function genId() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    let userId = localStorage.getItem('cji_user_id');
    if (!userId) {
        userId = genId();
        localStorage.setItem('cji_user_id', userId);
    }
    
    // session is per-tab
    const sessionId = genId();

    // --- Helpers ---
    function sanitiseUrl(urlStr) {
        try {
            const url = new URL(urlStr);
            return url.origin + url.pathname;
        } catch (e) {
            return urlStr.split('?')[0].split('#')[0];
        }
    }

    function getStepId(path) {
        // Fallback to exactly matching path to step_map if provided, else use raw path basename
        for (const [stepName, regexStr] of Object.entries(STEP_MAP)) {
            try {
                if (new RegExp(regexStr).test(path)) {
                    return stepName;
                }
            } catch (e) { }
        }
        let cleanPath = path.replace(/\/$/, "");
        return cleanPath ? cleanPath.substring(cleanPath.lastIndexOf('/') + 1) : "landing_page";
    }

    function getElementSelector(el) {
        if (!el || el.nodeType !== 1) return "";
        let selector = el.tagName.toLowerCase();
        if (el.id) {
            selector += "#" + el.id;
        } else if (el.className && typeof el.className === "string") {
            selector += "." + el.className.trim().replace(/\s+/g, '.');
        }
        return selector;
    }

    // --- Core Analytics ---
    function makeEvent(type, metadata = {}, targetElement = null) {
        return {
            timestamp: new Date().toISOString(),
            event_id: genId(),
            session_id: sessionId,
            user_id: userId,
            journey_name: JOURNEY_NAME,
            step_id: getStepId(window.location.pathname),
            event_type: type,
            url: sanitiseUrl(window.location.href),
            element_selectors: targetElement ? getElementSelector(targetElement) : null,
            metadata: metadata
        };
    }

    function flush() {
        if (eventQueue.length === 0) return;
        const currentBatch = [...eventQueue];
        eventQueue = [];

        const payload = JSON.stringify({
            api_key: API_KEY,
            events: currentBatch
        });

        if (navigator.sendBeacon && currentBatch.some(e => e.event_type === 'abandon')) {
            navigator.sendBeacon(ENDPOINT, payload);
        } else {
            fetch(ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CJI-Key': API_KEY
                },
                body: payload,
                keepalive: true
            }).catch(() => {
                // silently drop in realtime tracking to avoid spamming console
            });
        }
    }

    function push(event) {
        eventQueue.push(event);
        if (eventQueue.length >= BATCH_SIZE) {
            flush();
        } else if (!flushTimer) {
            flushTimer = setTimeout(() => {
                flush();
                flushTimer = null;
            }, FLUSH_INTERVAL);
        }
    }

    // --- Event Listeners ---
    
    // Page View
    document.addEventListener("DOMContentLoaded", () => {
        push(makeEvent("page_view", { title: document.title }));
    });

    // Clicks & Rage Clicks
    let lastClicks = [];
    document.addEventListener("click", (e) => {
        const now = Date.now();
        push(makeEvent("click", { click_x: e.clientX, click_y: e.clientY }, e.target));
        
        // Rage click detection
        lastClicks.push({ time: now, el: e.target, x: e.clientX, y: e.clientY });
        // filter older than 500ms
        lastClicks = lastClicks.filter(c => now - c.time <= 500);
        
        // Check if 3+ clicks on the same element
        const clicksOnTarget = lastClicks.filter(c => c.el === e.target);
        if (clicksOnTarget.length >= 3) {
            push(makeEvent("rage_click", {
                reason: "repeated_rapid_clicks",
                click_x: e.clientX,
                click_y: e.clientY
            }, e.target));
            // Reset to prevent spamming rage clicks continuously
            lastClicks = [];
        }
    }, true);

    // Form Submits
    document.addEventListener("submit", (e) => {
        push(makeEvent("form_submit", { 
            form_id: e.target.id || "unknown", 
            action: e.target.action 
        }, e.target));
    }, true);

    // Errors
    window.addEventListener("error", (e) => {
        push(makeEvent("error", { 
            message: e.message, 
            filename: e.filename, 
            lineno: e.lineno 
        }));
    });

    window.addEventListener("unhandledrejection", (e) => {
        push(makeEvent("error", { 
            code: "PROMISE_REJECTION", 
            reason: e.reason ? String(e.reason) : "Unknown Promise Rejection" 
        }));
    });

    // Abandonment
    window.addEventListener("beforeunload", () => {
        push(makeEvent("abandon", { time_on_page: "tracked" }));
        flush(); // Ensure we try to flush immediately via sendBeacon inside flush()
    });

    // SPA Navigation Interception (History API)
    function wrapHistory(type) {
        const orig = history[type];
        return function () {
            const rv = orig.apply(this, arguments);
            const e = new Event('cji_' + type);
            e.arguments = arguments;
            window.dispatchEvent(e);
            return rv;
        };
    }
    history.pushState = wrapHistory('pushState');
    history.replaceState = wrapHistory('replaceState');

    function handleNavigation() {
        push(makeEvent("step_complete", { reason: "navigation" }));
        setTimeout(() => push(makeEvent("page_view", { title: document.title })), 50);
    }

    window.addEventListener('cji_pushState', handleNavigation);
    window.addEventListener('cji_replaceState', handleNavigation);
    window.addEventListener('popstate', handleNavigation);

    // --- Public API ---
    window.CJITracker = {
        track: function(type, meta = {}) {
            push(makeEvent(type, meta));
        },
        getSessionId: () => sessionId
    };

})();
