import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/ws", () => ({
  createWSClient: vi.fn(() => ({ close: vi.fn() })),
}));
vi.mock("../lib/api", () => ({
  api: {
    createSession: vi.fn(),
    getSession: vi.fn(),
    scanSession: vi.fn(),
  },
}));

import { api } from "../lib/api";
import { useSessionStore } from "./session";

describe("R1-auto on opening a fresh month (rev-2 §7)", () => {
  beforeEach(() => {
    api.createSession.mockReset().mockResolvedValue({});
    api.getSession.mockReset();
    api.scanSession.mockReset().mockResolvedValue({});
  });

  it("auto-runs pase 1 when the opened month has no scanned data", async () => {
    api.getSession.mockResolvedValue({ session_id: "2026-04", cells: {} });
    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    // §B3 self-lend: runScan now carries the caller's own participant_id (via
    // getParticipantId()) so pase-1 doesn't skip a cell the launcher
    // themselves has open. This suite runs under the default "node"
    // environment (no jsdom/localStorage), where getParticipantId() is null —
    // still exercises the real call site, just without a browser identity.
    expect(api.scanSession).toHaveBeenCalledWith("2026-04", "all", null);
  });

  it("does NOT auto-scan a month that already has data", async () => {
    api.getSession.mockResolvedValue({
      session_id: "2026-04",
      cells: { HPV: { art: { count: 1 } } },
    });
    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    expect(api.scanSession).not.toHaveBeenCalled();
  });
});
