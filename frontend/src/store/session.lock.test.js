// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({
      session_id: "2026-04",
      cells: { HRB: { odi: { user_override: null, near_matches: [] } } },
    })),
    createSession: vi.fn(async () => ({})),
    listMonths: vi.fn(async () => ({ months: [] })),
    patchOverride: vi.fn(async () => ({ user_override: 5 })),
    patchPerFileOverride: vi.fn(async () => ({ new_cell_count: 3 })),
    patchWorkerCount: vi.fn(async () => ({ worker_marks: {}, worker_status: "pendiente", worker_cursor: null, worker_count: 0 })),
    patchNote: vi.fn(async () => ({ note: "", note_status: "resuelto", all_reliable: true })),
    patchConfirm: vi.fn(async () => ({ confirmed: true })),
    applyRatio: vi.fn(async () => ({ count: 3 })),
    reconcileWorkerMarks: vi.fn(async () => ({ worker_marks: {}, worker_count: 0 })),
    clearNearMatches: vi.fn(async () => ({})),
    presenceHeartbeat: vi.fn(async () => ({ participants: [] })),
    presenceFocus: vi.fn(async () => ({})),
    presenceLeave: vi.fn(async () => ({})),
    beaconLeave: vi.fn(),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useSessionStore } from "./session";
import { api } from "../lib/api";
import { toast } from "sonner";
import { setIdentity } from "../lib/identity";

const getState = () => useSessionStore.getState();

// Seed the store with a minimal open session so actions have something to work on.
function seedSession() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: { HRB: { odi: { user_override: null, near_matches: [], confirmed: false } } },
    },
  });
}

// Build a 409 error object that mirrors what jsonOrThrowStructured throws.
function make409(holderName = "Carla") {
  const err = new Error("cell_locked");
  err.status = 409;
  err.body = {
    detail: "cell_locked",
    hospital: "HRB",
    sigla: "odi",
    lock_holder: { participant_id: "p2", name: holderName, color: "#b", kind: "human", focused_cell: "HRB|odi", mode: "editor" },
  };
  return err;
}

beforeEach(() => {
  localStorage.clear();
  setIdentity({ name: "Daniel", color: "#ef4444" });
  vi.clearAllMocks();
  // Fresh session state before each test
  seedSession();
});

afterEach(() => {
  const h = getState()._visHandler;
  if (h) document.removeEventListener("visibilitychange", h);
  const hb = getState()._heartbeat;
  if (hb) clearInterval(hb);
  const uh = getState()._unloadHandler;
  if (uh) window.removeEventListener("pagehide", uh);
});

describe("Task 7a: api.patchOverride carries participant_id", () => {
  it("passes participantId in opts to patchOverride", async () => {
    api.patchOverride.mockResolvedValueOnce({ user_override: 5 });
    await getState().saveOverride("2026-04", "HRB", "odi", 5, {});
    expect(api.patchOverride).toHaveBeenCalledTimes(1);
    const [, , , , opts] = api.patchOverride.mock.calls[0];
    // participantId is a UUID string (minted from identity)
    expect(typeof opts.participantId).toBe("string");
    expect(opts.participantId.length).toBeGreaterThan(0);
  });
});

describe("Task 7b: saveOverride handles 409", () => {
  it("shows a toast with the lock holder's name on 409", async () => {
    api.patchOverride.mockRejectedValueOnce(make409("Carla"));
    await getState().saveOverride("2026-04", "HRB", "odi", 5, {});
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("Carla");
  });

  it("calls refetchSession (getSession) on 409", async () => {
    api.patchOverride.mockRejectedValueOnce(make409("Carla"));
    await getState().saveOverride("2026-04", "HRB", "odi", 5, {});
    // refetchSession calls api.getSession
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
  });

  it("does NOT set global error state on 409", async () => {
    api.patchOverride.mockRejectedValueOnce(make409("Carla"));
    await getState().saveOverride("2026-04", "HRB", "odi", 5, {});
    expect(getState().error).toBeNull();
  });

  it("clears the pending-save entry on 409 (no stuck 'saving' indicator)", async () => {
    api.patchOverride.mockRejectedValueOnce(make409("Carla"));
    await getState().saveOverride("2026-04", "HRB", "odi", 5, {});
    const key = "HRB|odi";
    expect(getState().pendingSaves[key]).toBeUndefined();
    expect(getState()._pendingSave.has(key)).toBe(false);
  });
});

describe("Task 7b: applyRatioCell passes participantId and handles 409", () => {
  it("passes participantId as 5th arg to applyRatio", async () => {
    api.applyRatio.mockResolvedValueOnce({ count: 3 });
    await getState().applyRatioCell("2026-04", "HRB", "odi", 1);
    expect(api.applyRatio).toHaveBeenCalledTimes(1);
    const args = api.applyRatio.mock.calls[0];
    // args: [sessionId, hospital, sigla, n, participantId]
    expect(typeof args[4]).toBe("string");
    expect(args[4].length).toBeGreaterThan(0);
  });

  it("shows toast and refetches on 409 without re-throwing", async () => {
    api.applyRatio.mockRejectedValueOnce(make409("Carla"));
    // Should NOT throw — 409 is handled
    await expect(getState().applyRatioCell("2026-04", "HRB", "odi", 1)).resolves.toBeUndefined();
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("Carla");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
    expect(getState().error).toBeNull();
  });
});

describe("Task 7b: clearNearMatches passes participantId and handles 409", () => {
  it("passes participantId as 5th arg to api.clearNearMatches", async () => {
    api.clearNearMatches.mockResolvedValueOnce({});
    await getState().clearNearMatches("2026-04", "HRB", "odi", null);
    expect(api.clearNearMatches).toHaveBeenCalledTimes(1);
    const args = api.clearNearMatches.mock.calls[0];
    expect(typeof args[4]).toBe("string");
    expect(args[4].length).toBeGreaterThan(0);
  });

  it("shows toast and refetches on 409, does not set error", async () => {
    api.clearNearMatches.mockRejectedValueOnce(make409("Carla"));
    await getState().clearNearMatches("2026-04", "HRB", "odi", null);
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("Carla");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
    expect(getState().error).toBeNull();
  });
});

describe("Task 7b: savePerFileOverride handles 409", () => {
  it("passes participantId in opts to patchPerFileOverride", async () => {
    api.patchPerFileOverride.mockResolvedValueOnce({ new_cell_count: 3 });
    await getState().savePerFileOverride("2026-04", "HRB", "odi", "a.pdf", 3);
    expect(api.patchPerFileOverride).toHaveBeenCalledTimes(1);
    const [, , , , , opts] = api.patchPerFileOverride.mock.calls[0];
    expect(typeof opts.participantId).toBe("string");
    expect(opts.participantId.length).toBeGreaterThan(0);
  });

  it("on 409 toasts, refetches, clears pending, and bumps filesTick (re-sync FileList)", async () => {
    const tickKey = "HRB|odi";
    const before = getState().filesTick?.[tickKey] ?? 0;
    api.patchPerFileOverride.mockRejectedValueOnce(make409("Carla"));
    await getState().savePerFileOverride("2026-04", "HRB", "odi", "a.pdf", 3);
    expect(toast.error.mock.calls[0][0]).toContain("Carla");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
    expect(getState().error).toBeNull();
    const key = "HRB|odi|a.pdf";
    expect(getState().pendingSaves[key]).toBeUndefined();
    expect(getState()._pendingSave.has(key)).toBe(false);
    expect(getState().filesTick[tickKey]).toBe(before + 1);
  });
});

describe("U2: savePerFileOverride handles a generic (non-409) error", () => {
  it("toasts and bumps filesTick (re-sync to server truth) instead of a sticky global error", async () => {
    const tickKey = "HRB|odi";
    const before = getState().filesTick?.[tickKey] ?? 0;
    api.patchPerFileOverride.mockRejectedValueOnce(new Error("network down"));
    await getState().savePerFileOverride("2026-04", "HRB", "odi", "a.pdf", 3);
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(getState().error).toBeNull();
    expect(getState().filesTick[tickKey]).toBe(before + 1);
  });
});

describe("F1 review fix: reconcileWorkerMarks distinguishes success from a handled 409", () => {
  it("returns the enriched cell on success (truthy → the panel may toast success)", async () => {
    const enriched = { worker_marks: { "a.pdf": [{ page: 1, count: 3 }] }, worker_count: 3 };
    api.reconcileWorkerMarks.mockResolvedValueOnce(enriched);
    const result = await getState().reconcileWorkerMarks("2026-04", "HRB", "odi", {
      action: "discard",
      from_file: "gone.pdf",
    });
    expect(result).toEqual(enriched);
  });

  it("returns NULL on 409 (falsy → the panel must NOT toast success), toasts the holder, refetches", async () => {
    api.reconcileWorkerMarks.mockRejectedValueOnce(make409("Carla"));
    const result = await getState().reconcileWorkerMarks("2026-04", "HRB", "odi", {
      action: "discard",
      from_file: "gone.pdf",
    });
    expect(result).toBeNull();
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("Carla");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
    expect(getState().error).toBeNull();
  });

  it("re-throws non-409 errors (the panel shows its failure toast)", async () => {
    const boom = new Error("500");
    boom.status = 500;
    api.reconcileWorkerMarks.mockRejectedValueOnce(boom);
    await expect(
      getState().reconcileWorkerMarks("2026-04", "HRB", "odi", {
        action: "discard",
        from_file: "gone.pdf",
      }),
    ).rejects.toBe(boom);
  });
});

describe("Task 7b: fallback toast message when lock_holder name is absent", () => {
  it("uses 'Otro usuario' when lock_holder.name is missing", async () => {
    const err = new Error("cell_locked");
    err.status = 409;
    err.body = { detail: "cell_locked" }; // no lock_holder
    api.patchOverride.mockRejectedValueOnce(err);
    await getState().saveOverride("2026-04", "HRB", "odi", 5, {});
    expect(toast.error.mock.calls[0][0]).toContain("Otro usuario");
  });
});
