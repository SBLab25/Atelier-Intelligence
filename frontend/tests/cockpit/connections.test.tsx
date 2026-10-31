import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConnectionsScreen } from "@/cockpit/components/screens/ConnectionsScreen";

describe("ConnectionsScreen", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const fetchMock = vi.fn().mockImplementation((url: string | URL | Request) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/connections/keys")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              ok: true,
              keys: [
                {
                  apiKey: "cji_live_mock_test_key_1234567890ab",
                  journeyName: "*",
                  description: "Primary Ingestion Key",
                  createdAt: new Date().toISOString(),
                  isActive: true,
                  isDev: false,
                },
              ],
              key: {
                apiKey: "cji_live_newly_minted_key_0987654321",
                journeyName: "partner_portal",
                description: "Key for Mobile Partner Portal",
                createdAt: new Date().toISOString(),
                isActive: true,
                isDev: false,
              },
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, count: 1 }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("renders header, multi-site connection cards, and key credentials manager", async () => {
    render(<ConnectionsScreen />);

    expect(screen.getByText("Client Connections & Multi-Site Ingestion")).toBeInTheDocument();
    expect(
      screen.getByText(/Integrate client websites and web applications with CJI/i)
    ).toBeInTheDocument();

    // Default site cards exist in the DOM
    expect(screen.getAllByText("Main E-Commerce Store").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("User Onboarding App")).toBeInTheDocument();
    expect(screen.getByText("Self-Serve Help Center")).toBeInTheDocument();
    expect(screen.getByText("Unified Cross-Site Ecosystem")).toBeInTheDocument();

    // Self-serve Key Manager card exists
    expect(screen.getByText("Client API Ingestion Keys")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generate Key/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Primary Ingestion Key")).toBeInTheDocument();
    });
  });

  it("updates code preview when switching between sites", () => {
    const { container } = render(<ConnectionsScreen />);

    // Initially active site is Main E-Commerce Store (checkout_funnel)
    const codeBlock = container.querySelector("pre");
    expect(codeBlock?.textContent).toContain('journey_name: "checkout_funnel"');

    // Switch to User Onboarding App
    const onboardingBtn = screen.getByText("User Onboarding App");
    fireEvent.click(onboardingBtn);

    expect(codeBlock?.textContent).toContain('journey_name: "user_onboarding"');

    // Switch to Unified Cross-Site Ecosystem (*)
    const unifiedBtn = screen.getByText("Unified Cross-Site Ecosystem");
    fireEvent.click(unifiedBtn);

    expect(codeBlock?.textContent).toContain('journey_name: "*"');
  });

  it("switches snippet format between HTML, React, Next.js, and cURL", () => {
    const { container } = render(<ConnectionsScreen />);

    // Default is HTML
    expect(screen.getByText("HTML Embed Snippet")).toBeInTheDocument();
    let codeBlock = container.querySelector("pre");
    expect(codeBlock?.textContent).toContain("<!-- CJI Client Telemetry Tracker Embed -->");

    // Switch to React Hook
    fireEvent.click(screen.getByRole("button", { name: /React Hook/i }));
    codeBlock = container.querySelector("pre");
    expect(codeBlock?.textContent).toContain("useCJITracker");

    // Switch to Next.js App Script
    fireEvent.click(screen.getByRole("button", { name: /Next\.js App Script/i }));
    codeBlock = container.querySelector("pre");
    expect(codeBlock?.textContent).toContain("CJITrackerScript");

    // Switch to cURL / REST API
    fireEvent.click(screen.getByRole("button", { name: /cURL \/ REST API/i }));
    codeBlock = container.querySelector("pre");
    expect(codeBlock?.textContent).toContain("curl -X POST");
  });

  it("allows registering a new client site dynamically and provisions its key", async () => {
    const { container } = render(<ConnectionsScreen />);

    // Click "Connect Site"
    const registerBtn = screen.getByRole("button", { name: /Connect Site/i });
    fireEvent.click(registerBtn);

    // Form inputs should appear
    const nameInput = screen.getByPlaceholderText(/e\.g\. Marketing Landing Page/i);
    const journeyInput = screen.getByPlaceholderText(/e\.g\. marketing_funnel/i);

    fireEvent.change(nameInput, { target: { value: "Mobile Partner Portal" } });
    fireEvent.change(journeyInput, { target: { value: "partner_portal" } });

    // Submit form
    const saveBtn = screen.getByRole("button", { name: /Save & Generate Snippet/i });
    fireEvent.click(saveBtn);

    // Should now appear in site list and header as selected
    await waitFor(() => {
      expect(screen.getAllByText("Mobile Partner Portal").length).toBeGreaterThanOrEqual(1);
    });

    const codeBlock = container.querySelector("pre");
    expect(codeBlock?.textContent).toContain('journey_name: "partner_portal"');
  });

  it("copies snippet to clipboard with visual feedback", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<ConnectionsScreen />);

    const copyBtn = screen.getByRole("button", { name: /Copy Code/i });
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalled();
    expect(screen.getByText("Copied!")).toBeInTheDocument();
  });

  it("toggles key reveal and generates a new key via the self-serve key manager", async () => {
    render(<ConnectionsScreen />);

    await waitFor(() => {
      expect(screen.getByText("Primary Ingestion Key")).toBeInTheDocument();
    });

    // Toggle reveal key
    const revealBtn = screen.getByTitle("Reveal Key");
    fireEvent.click(revealBtn);
    expect(screen.getByText("cji_live_mock_test_key_1234567890ab")).toBeInTheDocument();

    // Click Generate Key button
    const generateBtn = screen.getByRole("button", { name: /Generate Key/i });
    fireEvent.click(generateBtn);

    // Key creation form inputs
    const descInput = screen.getByPlaceholderText(/e\.g\. Production iOS Webview Key/i);
    fireEvent.change(descInput, { target: { value: "Self-Serve iOS Key" } });

    const submitKeyBtn = screen.getByRole("button", { name: /Generate & Save Key/i });
    fireEvent.click(submitKeyBtn);

    await waitFor(() => {
      expect(screen.getByText("Key for Mobile Partner Portal")).toBeInTheDocument();
    });
  });

  it("sends a live test ping and displays successful status", async () => {
    render(<ConnectionsScreen />);

    const pingBtn = screen.getByRole("button", { name: /Send Test Ping/i });
    fireEvent.click(pingBtn);

    await waitFor(() => {
      expect(screen.getByText(/Telemetric ping delivered!/i)).toBeInTheDocument();
    });
  });
});
