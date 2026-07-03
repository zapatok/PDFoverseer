// @vitest-environment jsdom
//
// Fix A (Fase-6 review): the F15 pending-save guard drops each write's own
// cell_updated echo — the full-snapshot broadcast that used to restore the
// backend-recomputed `all_reliable` in the writer's tab. The HTTP response is
// now the only channel, so savePerFileOverride / saveWorkerCount must merge
// `result.all_reliable` into the cell (the saveNote pattern, session.js).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({
      session_id: "2026-04",
      cells: { HRB: { odi: { all_reliable: false } } },
    })),
    patchPerFileOverride: vi.fn(async () => ({ new_cell_count: 3 })),
    patchWorkerCount: vi.fn(async () => ({
      worker_marks: {},
      worker_status: "pendiente",
      worker_cursor: null,
      worker_count: 0,
    })),
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
import { setIdentity } from "../lib/identity";

const getState = () => useSessionStore.getState();

function seedSession() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: {
        HRB: {
          odi: { all_reliable: false, per_file: { "big.pdf": 1 } },
          maquinaria: { all_reliable: false, worker_marks: {} },
        },
      },
    },
    _pendingSave: new Map(),
    pendingSaves: {},
    filesTick: {},
  });
}

beforeEach(() => {
  localStorage.clear();
  setIdentity({ name: "Daniel", color: "#ef4444" });
  vi.clearAllMocks();
  seedSession();
});

afterEach(() => {
  const hb = getState()._heartbeat;
  if (hb) clearInterval(hb);
});

describe("savePerFileOverride merges all_reliable from the response", () => {
  it("cell carries all_reliable: true after the save resolves", async () => {
    api.patchPerFileOverride.mockResolvedValueOnce({
      new_cell_count: 4,
      all_reliable: true,
    });
    await getState().savePerFileOverride("2026-04", "HRB", "odi", "big.pdf", 4);
    const cell = getState().session.cells.HRB.odi;
    expect(cell.all_reliable).toBe(true);
    expect(cell.per_file_overrides["big.pdf"]).toBe(4); // existing merge intact
  });
});

describe("saveWorkerCount merges all_reliable from the response", () => {
  it("cell carries all_reliable: true after terminado resolves", async () => {
    api.patchWorkerCount.mockResolvedValueOnce({
      worker_marks: { "maq.pdf": [{ page: 1, count: 9 }] },
      worker_status: "terminado",
      worker_cursor: null,
      worker_count: 9,
      all_reliable: true,
    });
    await getState().saveWorkerCount("2026-04", "HRB", "maquinaria", {
      status: "terminado",
    });
    const cell = getState().session.cells.HRB.maquinaria;
    expect(cell.all_reliable).toBe(true);
    expect(cell.worker_status).toBe("terminado"); // existing merge intact
  });
});
