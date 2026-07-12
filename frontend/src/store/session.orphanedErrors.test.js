// @vitest-environment jsdom
// §A2 — errores huérfanos → toasts. Before this fix, scanOcr/cancelScan/
// scanFileOcr/clearNearMatches and the file_scan_error WS case set the
// sticky global `error` banner, which only renders in MonthOverview — a
// failure while the operator is inside a hospital/cell view was invisible
// until they navigated back to the month. These five paths must toast
// instead (U2 pattern) and leave `error` untouched.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({
      session_id: "2026-04",
      cells: { HRB: { odi: { user_override: null, near_matches: [] } } },
    })),
    createSession: vi.fn(async () => ({})),
    listMonths: vi.fn(async () => ({ months: [] })),
    scanOcr: vi.fn(async () => { throw new Error("ECONNREFUSED"); }),
    cancelScan: vi.fn(async () => { throw new Error("ECONNREFUSED"); }),
    scanFileOcr: vi.fn(async () => { throw new Error("ECONNREFUSED"); }),
    clearNearMatches: vi.fn(async () => { throw new Error("ECONNREFUSED"); }),
    generateOutput: vi.fn(async () => { throw new Error("disk full"); }),
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
      // no HRB|odi cell → totalPdfsForPairs returns 0 → scanOcr never hits
      // the window.confirm cost guard (unrelated to this fix, §A5).
      cells: {},
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

describe("scanOcr on failure", () => {
  it("toasts naming the operation and does NOT set the sticky banner", async () => {
    await getState().scanOcr("2026-04", [["HRB", "odi"]]);
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("escaneo OCR");
    expect(getState().error).toBeNull();
  });
});

describe("cancelScan on failure", () => {
  it("toasts naming the operation and does NOT set the sticky banner", async () => {
    await getState().cancelScan("2026-04");
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("cancelar el escaneo");
    expect(getState().error).toBeNull();
  });
});

describe("scanFileOcr on a generic (non-409) failure", () => {
  it("toasts naming the operation and does NOT set the sticky banner", async () => {
    await getState().scanFileOcr("2026-04", "HRB", "odi", "a.pdf");
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain("escanear el archivo");
    expect(getState().error).toBeNull();
  });
});

describe("clearNearMatches on a generic (non-409) failure", () => {
  it("toasts naming the operation and does NOT set the sticky banner", async () => {
    useSessionStore.setState({
      session: { session_id: "2026-04", cells: { HRB: { odi: { near_matches: [] } } } },
    });
    await getState().clearNearMatches("2026-04", "HRB", "odi", null);
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(getState().error).toBeNull();
  });
});

describe("file_scan_error WS event on a generic failure", () => {
  it("toasts naming the operation and does NOT set the sticky banner", () => {
    getState()._handleWSEvent({
      type: "file_scan_error",
      hospital: "HRB",
      sigla: "odi",
      error: "boom",
    });
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(getState().error).toBeNull();
  });
});

describe("generateOutput on failure", () => {
  it("does NOT set the sticky banner (the caller's own toast is the only surface)", async () => {
    await expect(getState().generateOutput("2026-04")).rejects.toThrow();
    expect(getState().error).toBeNull();
    expect(getState().loading).toBe(false);
  });
});
