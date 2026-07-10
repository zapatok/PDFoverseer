// @vitest-environment jsdom
// U2 backport: a generic (non-409) save failure toasts + marks the cell's
// pendingSave as "error" — it must NOT set the sticky global error banner
// (that field is reserved for month-open/scan/export failures). Twin of the
// 409 coverage in session.lock.test.js.
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

function seedSession() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: { HRB: { odi: { user_override: null, near_matches: [], confirmed: false } } },
    },
  });
}

beforeEach(() => {
  localStorage.clear();
  setIdentity({ name: "Daniel", color: "#ef4444" });
  vi.clearAllMocks();
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

const boom = () => new Error("ECONNREFUSED");

describe("saveOverride on a generic failure", () => {
  it("toasts, marks the pendingSave as error, and does NOT set the sticky banner", async () => {
    api.patchOverride.mockRejectedValueOnce(boom());
    await getState().saveOverride("2026-04", "HRB", "odi", 5, {});
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("No se pudo guardar el conteo");
    expect(getState().error).toBeNull();
    expect(getState().pendingSaves["HRB|odi"]).toBe("error");
  });
});

describe("confirmCell on a generic failure", () => {
  it("toasts, reverts the optimistic flag, and does NOT set the sticky banner", async () => {
    api.patchConfirm.mockRejectedValueOnce(boom());
    await getState().confirmCell("2026-04", "HRB", "odi", true);
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("No se pudo actualizar el estado");
    expect(getState().error).toBeNull();
    // Optimistic true was reverted back to false.
    expect(getState().session.cells.HRB.odi.confirmed).toBe(false);
    expect(getState().pendingSaves["HRB|odi|confirm"]).toBe("error");
  });
});

describe("saveWorkerCount on a generic failure", () => {
  it("toasts and does NOT set the sticky banner", async () => {
    api.patchWorkerCount.mockRejectedValueOnce(boom());
    await getState().saveWorkerCount("2026-04", "HRB", "odi", { marks: {} });
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("No se pudo guardar el avance");
    expect(getState().error).toBeNull();
    expect(getState().pendingSaves["HRB|odi|workers"]).toBe("error");
  });
});

describe("saveNote on a generic failure", () => {
  it("toasts and does NOT set the sticky banner", async () => {
    api.patchNote.mockRejectedValueOnce(boom());
    await getState().saveNote("2026-04", "HRB", "odi", { text: "x" });
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("No se pudo guardar la nota");
    expect(getState().error).toBeNull();
    expect(getState().pendingSaves["HRB|odi|note"]).toBe("error");
  });
});
