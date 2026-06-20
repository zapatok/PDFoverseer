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

import { useSessionStore } from "./session";
import { api } from "../lib/api";
import { setIdentity, HEARTBEAT_MS } from "../lib/identity";

// Helper: returns current store state
const getState = () => useSessionStore.getState();

describe("presence: _handleWSEvent presence case", () => {
  beforeEach(() => {
    localStorage.clear();
    setIdentity({ name: "TestUser", color: "#ef4444" });
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up visibilitychange listener
    const h = getState()._visHandler;
    if (h) document.removeEventListener("visibilitychange", h);
    // Clean up heartbeat interval
    const hb = getState()._heartbeat;
    if (hb) clearInterval(hb);
    // Clean up unload handler
    const uh = getState()._unloadHandler;
    if (uh) window.removeEventListener("pagehide", uh);
  });

  it("sets presence state from a presence WS event", () => {
    const participants = [
      { participant_id: "p2", name: "C", color: "#b", focused_cell: null },
    ];
    getState()._handleWSEvent({ type: "presence", participants });
    expect(getState().presence).toEqual(participants);
  });

  it("defaults to [] if participants is missing", () => {
    // Start from a non-empty state
    getState()._handleWSEvent({ type: "presence", participants: [{ participant_id: "x", name: "X", color: "#0", focused_cell: null }] });
    getState()._handleWSEvent({ type: "presence" });
    expect(getState().presence).toEqual([]);
  });
});

describe("presence: openMonth starts heartbeat", () => {
  beforeEach(() => {
    localStorage.clear();
    setIdentity({ name: "TestUser", color: "#ef4444" });
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    // Clean up visibilitychange listener
    const h = getState()._visHandler;
    if (h) document.removeEventListener("visibilitychange", h);
    // Clean up heartbeat interval
    const hb = getState()._heartbeat;
    if (hb) clearInterval(hb);
    // Clean up unload handler
    const uh = getState()._unloadHandler;
    if (uh) window.removeEventListener("pagehide", uh);
  });

  it("calls presenceHeartbeat immediately on openMonth and seeds presence", async () => {
    api.presenceHeartbeat.mockResolvedValue({ participants: [{ participant_id: "p1", name: "TestUser", color: "#ef4444", focused_cell: null }] });

    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    // Flush any micro-tasks from the immediate beat() call
    await Promise.resolve();

    expect(api.presenceHeartbeat).toHaveBeenCalledTimes(1);
    const callArgs = api.presenceHeartbeat.mock.calls[0];
    expect(callArgs[0]).toBe("2026-04");
    expect(callArgs[1]).toMatchObject({ name: "TestUser", color: "#ef4444" });
    expect(callArgs[1].participant_id).toBeTruthy();

    // presence seeded from the heartbeat response
    expect(getState().presence).toEqual([{ participant_id: "p1", name: "TestUser", color: "#ef4444", focused_cell: null }]);
  });

  it("fires a second heartbeat after HEARTBEAT_MS", async () => {
    api.presenceHeartbeat.mockResolvedValue({ participants: [] });

    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    await Promise.resolve(); // flush immediate beat

    const countAfterOpen = api.presenceHeartbeat.mock.calls.length;

    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS);

    expect(api.presenceHeartbeat.mock.calls.length).toBe(countAfterOpen + 1);
  });
});

describe("presence: setFocus", () => {
  beforeEach(async () => {
    localStorage.clear();
    setIdentity({ name: "TestUser", color: "#ef4444" });
    vi.clearAllMocks();
    api.presenceHeartbeat.mockResolvedValue({ participants: [] });
    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    await Promise.resolve();
  });

  afterEach(() => {
    const h = getState()._visHandler;
    if (h) document.removeEventListener("visibilitychange", h);
    const hb = getState()._heartbeat;
    if (hb) clearInterval(hb);
    const uh = getState()._unloadHandler;
    if (uh) window.removeEventListener("pagehide", uh);
  });

  it("calls presenceFocus with session id and cell", () => {
    getState().setFocus("HRB|odi");
    expect(api.presenceFocus).toHaveBeenCalledTimes(1);
    const [sid, body] = api.presenceFocus.mock.calls[0];
    expect(sid).toBe("2026-04");
    expect(body.cell).toBe("HRB|odi");
    expect(body.participant_id).toBeTruthy();
  });
});

describe("presence: re-openMonth clears previous interval", () => {
  beforeEach(() => {
    localStorage.clear();
    setIdentity({ name: "TestUser", color: "#ef4444" });
    vi.clearAllMocks();
    vi.useFakeTimers();
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

  it("only fires one heartbeat per interval after re-openMonth (no accumulation)", async () => {
    api.presenceHeartbeat.mockResolvedValue({ participants: [] });

    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    await Promise.resolve(); // flush immediate beat from first open

    await useSessionStore.getState().openMonth("2026-05", 2026, 5);
    await Promise.resolve(); // flush immediate beat from second open

    // Clear call count after both opens settled
    api.presenceHeartbeat.mockClear();

    // Advance one interval: should produce exactly ONE beat (not two from stale interval)
    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS);

    expect(api.presenceHeartbeat).toHaveBeenCalledTimes(1);
  });
});

describe("presence: identity-null guard", () => {
  beforeEach(() => {
    localStorage.clear(); // no identity set
    vi.clearAllMocks();
  });

  afterEach(() => {
    const h = getState()._visHandler;
    if (h) document.removeEventListener("visibilitychange", h);
    const hb = getState()._heartbeat;
    if (hb) clearInterval(hb);
    const uh = getState()._unloadHandler;
    if (uh) window.removeEventListener("pagehide", uh);
  });

  it("startPresence does not call presenceHeartbeat when no identity", async () => {
    api.getSession.mockResolvedValue({ session_id: "2026-04", cells: {} });
    api.presenceHeartbeat.mockResolvedValue({ participants: [] });

    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    await Promise.resolve();

    expect(api.presenceHeartbeat).not.toHaveBeenCalled();
  });

  it("setFocus does not call presenceFocus when no identity", async () => {
    api.getSession.mockResolvedValue({ session_id: "2026-04", cells: {} });
    await useSessionStore.getState().openMonth("2026-04", 2026, 4);

    getState().setFocus("HRB|odi");
    expect(api.presenceFocus).not.toHaveBeenCalled();
  });
});
