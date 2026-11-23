// @vitest-environment node
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";

// Mock session and loaders/mutations
const mockSession = vi.fn();
vi.mock("@/lib/session", () => ({
  getSession: () => mockSession(),
}));

const mockListRuns = vi.fn();
const mockGetRun = vi.fn();
const mockGetRunResults = vi.fn();
vi.mock("@/lib/api/loaders", () => ({
  listRuns: (status?: string) => mockListRuns(status),
  getRun: (runId: string) => mockGetRun(runId),
  getRunResults: (runId: string) => mockGetRunResults(runId),
  RUN_STATUSES: ["running", "awaiting_approval", "approved", "completed", "failed"],
}));

const mockStartRun = vi.fn();
const mockApproveRun = vi.fn();
const mockResumeRun = vi.fn();
vi.mock("@/lib/api/mutations", () => ({
  startRun: (body: any, key: string) => mockStartRun(body, key),
  approveRun: (runId: string, key: string) => mockApproveRun(runId, key),
  resumeRun: (runId: string, key: string) => mockResumeRun(runId, key),
}));

describe("Runs API Route Handlers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("GET /api/runs & POST /api/runs", () => {
    it("rejects unauthenticated requests with 401", async () => {
      mockSession.mockResolvedValue(null);
      const { GET, POST } = await import("@/app/api/runs/route");

      const getReq = new NextRequest("http://localhost/api/runs");
      const getRes = await GET(getReq);
      expect(getRes.status).toBe(401);

      const postReq = new NextRequest("http://localhost/api/runs", {
        method: "POST",
        body: JSON.stringify({ journey_id: "test" }),
      });
      const postRes = await POST(postReq);
      expect(postRes.status).toBe(401);
    });

    it("rejects run creation by viewer with 403", async () => {
      mockSession.mockResolvedValue({ role: "viewer", tokenId: "u1", label: "Viewer" });
      const { POST } = await import("@/app/api/runs/route");

      const req = new NextRequest("http://localhost/api/runs", {
        method: "POST",
        body: JSON.stringify({ journey_id: "quest_journey" }),
      });
      const res = await POST(req);
      expect(res.status).toBe(403);
    });

    it("lists runs when authenticated as viewer or operator", async () => {
      mockSession.mockResolvedValue({ role: "viewer", tokenId: "u1" });
      mockListRuns.mockResolvedValue({
        ok: true,
        data: {
          items: [
            { run_id: "run-1", journey_id: "quest_journey", status: "completed" },
          ],
          page_info: { has_next: false, end_cursor: null },
        },
      });

      const { GET } = await import("@/app/api/runs/route");
      const req = new NextRequest("http://localhost/api/runs?status=completed");
      const res = await GET(req);
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.ok).toBe(true);
      expect(json.data.items[0].run_id).toBe("run-1");
      expect(mockListRuns).toHaveBeenCalledWith("completed");
    });

    it("starts a LangGraph run when authenticated as operator", async () => {
      mockSession.mockResolvedValue({ role: "operator", tokenId: "op1" });
      mockStartRun.mockResolvedValue({
        ok: true,
        data: {
          run_id: "run-new-123",
          journey_id: "quest_journey",
          status: "running",
          steps: {},
        },
      });

      const { POST } = await import("@/app/api/runs/route");
      const req = new NextRequest("http://localhost/api/runs", {
        method: "POST",
        body: JSON.stringify({
          journey_id: "quest_journey",
          auto_approve: false,
          window_minutes: 30,
        }),
      });
      const res = await POST(req);
      expect(res.status).toBe(202);
      const json = await res.json();
      expect(json.ok).toBe(true);
      expect(json.data.run_id).toBe("run-new-123");
      expect(mockStartRun).toHaveBeenCalledWith(
        expect.objectContaining({
          journey_id: "quest_journey",
          auto_approve: false,
          window_minutes: 30,
        }),
        expect.any(String)
      );
    });
  });

  describe("GET /api/runs/[runId]", () => {
    it("returns run details with step states", async () => {
      mockSession.mockResolvedValue({ role: "operator", tokenId: "op1" });
      mockGetRun.mockResolvedValue({
        ok: true,
        data: {
          run_id: "run-xyz",
          status: "running",
          steps: {
            ingestion_worker: { status: "completed" },
            data_worker: { status: "running" },
          },
        },
      });

      const { GET } = await import("@/app/api/runs/[runId]/route");
      const req = new NextRequest("http://localhost/api/runs/run-xyz");
      const res = await GET(req, { params: Promise.resolve({ runId: "run-xyz" }) });
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.ok).toBe(true);
      expect(json.data.steps.ingestion_worker.status).toBe("completed");
      expect(mockGetRun).toHaveBeenCalledWith("run-xyz");
    });
  });

  describe("POST /api/runs/[runId]/approve & resume", () => {
    it("approves an awaiting run when operator", async () => {
      mockSession.mockResolvedValue({ role: "operator", tokenId: "op1" });
      mockApproveRun.mockResolvedValue({
        ok: true,
        data: {
          run_id: "run-xyz",
          approved: true,
        },
      });

      const { POST } = await import("@/app/api/runs/[runId]/approve/route");
      const req = new NextRequest("http://localhost/api/runs/run-xyz/approve", {
        method: "POST",
        body: JSON.stringify({}),
      });
      const res = await POST(req, { params: Promise.resolve({ runId: "run-xyz" }) });
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.ok).toBe(true);
      expect(mockApproveRun).toHaveBeenCalledWith("run-xyz", expect.any(String));
    });

    it("resumes a failed or interrupted run", async () => {
      mockSession.mockResolvedValue({ role: "operator", tokenId: "op1" });
      mockResumeRun.mockResolvedValue({
        ok: true,
        data: {
          run_id: "run-xyz",
          status: "running",
        },
      });

      const { POST } = await import("@/app/api/runs/[runId]/resume/route");
      const req = new NextRequest("http://localhost/api/runs/run-xyz/resume", {
        method: "POST",
        body: JSON.stringify({}),
      });
      const res = await POST(req, { params: Promise.resolve({ runId: "run-xyz" }) });
      expect(res.status).toBe(202);
      const json = await res.json();
      expect(json.ok).toBe(true);
      expect(mockResumeRun).toHaveBeenCalledWith("run-xyz", expect.any(String));
    });
  });

  describe("GET /api/runs/[runId]/results", () => {
    it("returns run results including friction scores and insights", async () => {
      mockSession.mockResolvedValue({ role: "viewer", tokenId: "v1" });
      mockGetRunResults.mockResolvedValue({
        ok: true,
        data: {
          run_id: "run-xyz",
          status: "completed",
          report_id: "rep-123",
          insights: [{ insight_id: "ins-1", title: "Checkout Bottleneck" }],
          friction_scores: [{ step_id: "payment", score: 85, is_critical: true }],
        },
      });

      const { GET } = await import("@/app/api/runs/[runId]/results/route");
      const req = new NextRequest("http://localhost/api/runs/run-xyz/results");
      const res = await GET(req, { params: Promise.resolve({ runId: "run-xyz" }) });
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.ok).toBe(true);
      expect(json.data.report_id).toBe("rep-123");
      expect(json.data.insights.length).toBe(1);
    });
  });
});
