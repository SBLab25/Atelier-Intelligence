import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  initCJITracker,
  trackEvent,
  trackStep,
  identifyUser,
  flushEvents,
  CJIConfig,
} from "@/lib/tracker";

describe("Client Tracking SDK (@cji/tracker)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    delete window.CJI_CONFIG;
    delete window.CJITracker;
    document.querySelectorAll('script[data-cji-tracker="true"]').forEach((s) => s.remove());
  });

  afterEach(() => {
    localStorage.clear();
    delete window.CJI_CONFIG;
    delete window.CJITracker;
  });

  it("configures window.CJI_CONFIG and injects tracker script element", () => {
    const config: CJIConfig = {
      api_key: "cji_live_test_key_123",
      journey_name: "checkout_funnel",
      collector_url: "http://localhost:8000/collect/batch",
    };

    initCJITracker(config);

    expect(window.CJI_CONFIG).toBeDefined();
    expect(window.CJI_CONFIG?.api_key).toBe("cji_live_test_key_123");
    expect(window.CJI_CONFIG?.journey_name).toBe("checkout_funnel");

    const injectedScript = document.querySelector('script[data-cji-tracker="true"]') as HTMLScriptElement;
    expect(injectedScript).toBeInTheDocument();
    expect(injectedScript.src).toContain("http://localhost:8000/tracker.js");
    expect(injectedScript.defer).toBe(true);
  });

  it("does not duplicate script element if already present", () => {
    const config: CJIConfig = {
      api_key: "cji_live_test_key_123",
      journey_name: "checkout_funnel",
      collector_url: "http://localhost:8000/collect/batch",
    };

    initCJITracker(config);
    initCJITracker(config);

    const scripts = document.querySelectorAll('script[data-cji-tracker="true"]');
    expect(scripts.length).toBe(1);
  });

  it("delegates trackEvent, trackStep, and identifyUser to window.CJITracker", () => {
    const mockTrack = vi.fn();
    const mockTrackStep = vi.fn();
    const mockIdentify = vi.fn();
    const mockFlush = vi.fn();

    window.CJITracker = {
      track: mockTrack,
      trackStep: mockTrackStep,
      identify: mockIdentify,
      flush: mockFlush,
      getSessionId: () => "sess-123",
      getUserId: () => "usr-123",
      getCurrentStep: () => "cart",
      getDwellMs: () => 1500,
      getQueueLength: () => 0,
    };

    trackEvent("click", { button_id: "pay_now" });
    expect(mockTrack).toHaveBeenCalledWith("click", { button_id: "pay_now" }, undefined);

    trackStep("shipping_selection");
    expect(mockTrackStep).toHaveBeenCalledWith("shipping_selection");

    identifyUser("cust-456", { plan: "pro" });
    expect(mockIdentify).toHaveBeenCalledWith("cust-456", { plan: "pro" });

    flushEvents();
    expect(mockFlush).toHaveBeenCalled();
  });

  it("gracefully handles tracking calls when tracker script is not yet ready", () => {
    expect(() => {
      trackEvent("page_view", { title: "Home" });
      trackStep("landing");
      identifyUser("cust-999");
      flushEvents();
    }).not.toThrow();
  });
});
