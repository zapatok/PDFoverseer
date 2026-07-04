// @vitest-environment jsdom
// Anti-colados store action: dismissColadoSuspect merges the backend's
// { colado_suspects (open list), all_reliable } into the cell; 409 → lock
// toast + refetch; 404 → neutral toast + refetch; generic → toast, no sticky.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({
      session_id: "2026-04",
      cells: { HRB: { chps: { colado_suspects: [], all_reliable: true } } },
    })),
    createSession: vi.fn(async () => ({})),
    listMonths: vi.fn(async () => ({ months: [] })),
    dismissColadoSuspect: vi.fn(async () => ({ colado_suspects: [], all_reliable: true })),
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

function seed() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: {
        HRB: {
          chps: {
            colado_suspects: [{ id: "cs_a", kind: "filename", file: "x.pdf", counted: true }],
            all_reliable: false,
          },
        },
      },
    },
  });
}

beforeEach(() => {
  localStorage.clear();
  setIdentity({ name: "Daniel", color: "#ef4444" });
  vi.clearAllMocks();
  seed();
});

afterEach(() => {
  const h = getState()._visHandler;
  if (h) document.removeEventListener("visibilitychange", h);
});

function make(status, holderName) {
  const err = new Error(status === 409 ? "cell_locked" : "not found");
  err.status = status;
  if (status === 409) {
    err.body = { detail: "cell_locked", lock_holder: { name: holderName } };
  }
  return err;
}

describe("dismissColadoSuspect", () => {
  it("merges the open list + all_reliable into the cell on success", async () => {
    api.dismissColadoSuspect.mockResolvedValueOnce({ colado_suspects: [], all_reliable: true });
    await getState().dismissColadoSuspect("2026-04", "HRB", "chps", "cs_a");
    const cell = getState().session.cells.HRB.chps;
    expect(cell.colado_suspects).toEqual([]);
    expect(cell.all_reliable).toBe(true);
  });

  it("on 409 toasts the lock holder + refetches, does NOT set sticky error", async () => {
    api.dismissColadoSuspect.mockRejectedValueOnce(make(409, "Carla"));
    await getState().dismissColadoSuspect("2026-04", "HRB", "chps", "cs_a");
    expect(toast.error.mock.calls[0][0]).toContain("Carla");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
    expect(getState().error).toBeNull();
  });

  it("on 404 toasts 'ya no existe' + refetches", async () => {
    api.dismissColadoSuspect.mockRejectedValueOnce(make(404));
    await getState().dismissColadoSuspect("2026-04", "HRB", "chps", "cs_a");
    expect(toast.error.mock.calls[0][0]).toContain("ya no existe");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
  });

  it("on a generic error toasts, does NOT set sticky error", async () => {
    api.dismissColadoSuspect.mockRejectedValueOnce(new Error("boom"));
    await getState().dismissColadoSuspect("2026-04", "HRB", "chps", "cs_a");
    expect(toast.error.mock.calls[0][0]).toContain("No se pudo descartar");
    expect(getState().error).toBeNull();
  });
});
