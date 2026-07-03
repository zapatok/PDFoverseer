import { describe, it, expect, vi, beforeEach } from "vitest";

// F12: `toast` from sonner is both callable (the neutral variant) and carries
// `.error`/`.success` methods — mirror the real API shape (matches the U6
// convention in session.fileScanCancel.test.js).
vi.mock("sonner", () => {
  const toastFn = vi.fn();
  toastFn.error = vi.fn();
  toastFn.success = vi.fn();
  return { toast: toastFn };
});

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({
      session_id: "2026-04",
      cells: { HRB: { odi: { user_override: null, near_matches: [] } } },
    })),
  },
}));

import { useSessionStore } from "./session";
import { toast } from "sonner";
import { api } from "../lib/api";

describe("file_scan_error: cell_locked (F12 — merge-time lock re-check)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSessionStore.setState({
      session: {
        session_id: "2026-04",
        cells: { HRB: { odi: { user_override: null, near_matches: [] } } },
      },
      fileScan: {
        hospital: "HRB",
        sigla: "odi",
        filename: "a.pdf",
        page: 1,
        pagesTotal: 3,
        terminal: null,
      },
      filesTick: {},
      error: null,
    });
  });

  it("shows the lock-holder toast, not the sticky global error banner", () => {
    useSessionStore.getState()._handleWSEvent({
      type: "file_scan_error",
      hospital: "HRB",
      sigla: "odi",
      filename: "a.pdf",
      error: "cell_locked",
      lock_holder: { name: "Carla" },
    });

    expect(toast.error).toHaveBeenCalledWith("Carla está editando esta celda");
    expect(toast).not.toHaveBeenCalled();

    const state = useSessionStore.getState();
    expect(state.error).toBeNull();
    expect(state.fileScan.terminal).toBe("cancelled");
  });

  it("falls back to 'Otro usuario' when lock_holder is absent", () => {
    useSessionStore.getState()._handleWSEvent({
      type: "file_scan_error",
      hospital: "HRB",
      sigla: "odi",
      filename: "a.pdf",
      error: "cell_locked",
    });

    expect(toast.error).toHaveBeenCalledWith("Otro usuario está editando esta celda");
  });

  it("bumps filesTick and refetches the session (re-sync to server truth)", async () => {
    useSessionStore.getState()._handleWSEvent({
      type: "file_scan_error",
      hospital: "HRB",
      sigla: "odi",
      filename: "a.pdf",
      error: "cell_locked",
      lock_holder: { name: "Carla" },
    });

    expect(useSessionStore.getState().filesTick["HRB|odi"]).toBe(1);
    // refetchSession is fire-and-forget (async) — flush microtasks.
    await Promise.resolve();
    await Promise.resolve();
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
  });
});
