// @vitest-environment jsdom
// §A11 (second half) — the pase-1 scan gets its own truthful `scanning`
// flag, set ONLY by runScan (true at start, false at both exits). openMonth
// never touches it — a plain month open sets `loading` but must not light
// "Escaneando…". openMonth's first-open auto-scan fire-and-forgets runScan,
// whose own flag then lights the label correctly.
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    scanSession: vi.fn(async () => ({})),
    getSession: vi.fn(async () => ({ session_id: "2026-04", cells: {} })),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useSessionStore } from "./session";
import { api } from "../lib/api";
import { setIdentity } from "../lib/identity";

const getState = () => useSessionStore.getState();

beforeEach(() => {
  localStorage.clear();
  setIdentity({ name: "Daniel", color: "#ef4444" });
  vi.clearAllMocks();
  useSessionStore.setState({ loading: false, scanning: false, error: null });
});

describe("runScan's dedicated `scanning` flag", () => {
  it("is true while the pase-1 scan is in flight, false after it resolves", async () => {
    let sawScanningDuring = false;
    api.scanSession.mockImplementationOnce(async () => {
      sawScanningDuring = getState().scanning;
      return {};
    });
    await getState().runScan("2026-04");
    expect(sawScanningDuring).toBe(true);
    expect(getState().scanning).toBe(false);
    expect(getState().loading).toBe(false);
  });

  it("is cleared even when the scan fails", async () => {
    api.scanSession.mockRejectedValueOnce(new Error("boom"));
    await getState().runScan("2026-04");
    expect(getState().scanning).toBe(false);
  });
});
