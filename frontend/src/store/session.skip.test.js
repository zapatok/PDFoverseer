// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({ session_id: "2026-04", cells: {} })),
    createSession: vi.fn(async () => ({})),
    listMonths: vi.fn(async () => ({ months: [] })),
    presenceHeartbeat: vi.fn(async () => ({ participants: [] })),
    presenceFocus: vi.fn(async () => ({})),
    presenceLeave: vi.fn(async () => ({})),
    beaconLeave: vi.fn(),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useSessionStore } from "./session";

const getState = () => useSessionStore.getState();

function seedSession() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: { HRB: { odi: { user_override: null, near_matches: [] } } },
    },
    scanningCells: new Set(["HRB|odi", "HPV|charla"]),
    scanProgress: { done: 2, total: 5, unit: "pdf" },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  seedSession();
});

afterEach(() => {
  vi.useRealTimers();
  const h = getState()._visHandler;
  if (h) document.removeEventListener("visibilitychange", h);
  const hb = getState()._heartbeat;
  if (hb) clearInterval(hb);
  const uh = getState()._unloadHandler;
  if (uh) window.removeEventListener("pagehide", uh);
});

describe("Task 7: cell_skipped WS event", () => {
  it("does NOT mutate session.cells when a cell is skipped", () => {
    const cellsBefore = getState().session.cells;
    getState()._handleWSEvent({
      type: "cell_skipped",
      hospital: "HRB",
      sigla: "odi",
      reason: "locked",
      lock_holder: { participant_id: "p1", name: "Daniel", color: "#ef4444", kind: "human" },
    });
    // cells object should be the same reference or at least identical content
    expect(getState().session.cells).toEqual(cellsBefore);
  });

  it("accumulates skipped cells into scanProgress.skipped", () => {
    getState()._handleWSEvent({
      type: "cell_skipped",
      hospital: "HRB",
      sigla: "odi",
      reason: "locked",
      lock_holder: { participant_id: "p1", name: "Daniel", color: "#ef4444", kind: "human" },
    });
    expect(getState().scanProgress.skipped).toEqual([{ hospital: "HRB", sigla: "odi" }]);
  });

  it("accumulates multiple skipped cells", () => {
    getState()._handleWSEvent({
      type: "cell_skipped",
      hospital: "HRB",
      sigla: "odi",
      reason: "locked",
      lock_holder: { participant_id: "p1", name: "Daniel", color: "#ef4444", kind: "human" },
    });
    getState()._handleWSEvent({
      type: "cell_skipped",
      hospital: "HPV",
      sigla: "charla",
      reason: "locked",
      lock_holder: { participant_id: "p2", name: "Carla", color: "#22d3ee", kind: "human" },
    });
    expect(getState().scanProgress.skipped).toEqual([
      { hospital: "HRB", sigla: "odi" },
      { hospital: "HPV", sigla: "charla" },
    ]);
  });

  it("removes the cell from scanningCells when skipped", () => {
    getState()._handleWSEvent({
      type: "cell_skipped",
      hospital: "HRB",
      sigla: "odi",
      reason: "locked",
      lock_holder: { participant_id: "p1", name: "Daniel", color: "#ef4444", kind: "human" },
    });
    expect(getState().scanningCells.has("HRB|odi")).toBe(false);
  });

  it("handles cell_skipped when scanProgress is null (no-op on skipped array)", () => {
    useSessionStore.setState({ scanProgress: null });
    expect(() =>
      getState()._handleWSEvent({
        type: "cell_skipped",
        hospital: "HRB",
        sigla: "odi",
        reason: "locked",
        lock_holder: { participant_id: "p1", name: "Daniel", color: "#ef4444", kind: "human" },
      })
    ).not.toThrow();
  });
});

describe("Task 7: scan_complete.skipped handling", () => {
  it("copies skipped list from scan_complete into scanProgress.skipped", () => {
    getState()._handleWSEvent({
      type: "scan_complete",
      scanned: 3,
      errors: 0,
      cancelled: 0,
      skipped: [{ hospital: "HRB", sigla: "odi" }],
    });
    expect(getState().scanProgress.skipped).toEqual([{ hospital: "HRB", sigla: "odi" }]);
  });

  it("sets terminal='complete' on scan_complete with skipped cells", () => {
    getState()._handleWSEvent({
      type: "scan_complete",
      scanned: 3,
      errors: 0,
      cancelled: 0,
      skipped: [{ hospital: "HRB", sigla: "odi" }],
    });
    expect(getState().scanProgress.terminal).toBe("complete");
  });

  it("does NOT auto-dismiss after 5s when skipped.length > 0", () => {
    getState()._handleWSEvent({
      type: "scan_complete",
      scanned: 3,
      errors: 0,
      cancelled: 0,
      skipped: [{ hospital: "HRB", sigla: "odi" }],
    });
    vi.advanceTimersByTime(6000);
    // scanProgress must still be present (not auto-dismissed)
    expect(getState().scanProgress).not.toBeNull();
  });

  it("defaults skipped to [] when scan_complete has no skipped field", () => {
    getState()._handleWSEvent({
      type: "scan_complete",
      scanned: 5,
      errors: 0,
      cancelled: 0,
      // no 'skipped' field
    });
    expect(getState().scanProgress.skipped).toEqual([]);
  });

  it("auto-dismisses after 5s when skipped is empty (normal path)", () => {
    getState()._handleWSEvent({
      type: "scan_complete",
      scanned: 5,
      errors: 0,
      cancelled: 0,
      skipped: [],
    });
    expect(getState().scanProgress).not.toBeNull(); // present before timeout
    vi.advanceTimersByTime(5000);
    expect(getState().scanProgress).toBeNull();     // auto-dismissed
  });
});
