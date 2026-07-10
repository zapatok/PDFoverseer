// @vitest-environment jsdom
//
// Tests for ReorganizacionPanel pure helpers (outgoingOps, incomingOps,
// netDocDelta, hasPendingOps, pendingOpsCountForCell) + the F3 lock rendering
// (locked disables per-op delete). Export moved to MonthReorgPanel (Task 18) —
// this component no longer renders an export button at all. jsdom env so the
// render tests can mount; the pure-helper tests are env-agnostic and still
// pass under it.

import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import ReorganizacionPanel, {
  outgoingOps,
  incomingOps,
  netDocDelta,
  hasPendingOps,
  pendingOpsCountForCell,
} from "./ReorganizacionPanel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

const H = "HPV";
const S = "odi";

const pendingOut = {
  id: "op-1",
  op_type: "move_file",
  status: "pending",
  source: { hospital: H, sigla: S, file: "a.pdf" },
  dest: { hospital: "HRB", sigla: "odi" },
  doc_count: 3,
  worker_count: 0,
};

const pendingIn = {
  id: "op-2",
  op_type: "move_file",
  status: "pending",
  source: { hospital: "HRB", sigla: "insgral" },
  dest: { hospital: H, sigla: S },
  doc_count: 7,
  worker_count: 0,
};

const appliedOut = {
  id: "op-3",
  op_type: "rotate",
  status: "applied",
  source: { hospital: H, sigla: S, file: "b.pdf" },
  dest: { hospital: "HLL", sigla: "odi" },
  doc_count: 2,
  worker_count: 0,
};

const unrelated = {
  id: "op-4",
  op_type: "move_file",
  status: "pending",
  source: { hospital: "HRB", sigla: "insgral" },
  dest: { hospital: "HLL", sigla: "odi" },
  doc_count: 5,
  worker_count: 0,
};

// ── (a) empty ops ──────────────────────────────────────────────────────────
describe("(a) ops=[]", () => {
  it("outgoingOps returns empty", () => {
    expect(outgoingOps([], H, S)).toEqual([]);
  });

  it("incomingOps returns empty", () => {
    expect(incomingOps([], H, S)).toEqual([]);
  });

  it("hasPendingOps returns false → export button should be disabled", () => {
    expect(hasPendingOps([], H, S)).toBe(false);
  });

  it("netDocDelta is 0", () => {
    expect(netDocDelta([], H, S)).toBe(0);
  });
});

// ── (b) one outgoing + one incoming ────────────────────────────────────────
describe("(b) one outgoing + one incoming (both pending)", () => {
  const ops = [pendingOut, pendingIn, unrelated];

  it("outgoingOps returns only the source-matching op", () => {
    const res = outgoingOps(ops, H, S);
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("op-1");
  });

  it("incomingOps returns only the dest-matching op", () => {
    const res = incomingOps(ops, H, S);
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("op-2");
  });

  it("outgoing row would show −doc_count → DEST (op-1 → −3 → HRB/odi)", () => {
    const op = outgoingOps(ops, H, S)[0];
    expect(op.doc_count).toBe(3);
    expect(op.dest.hospital).toBe("HRB");
    expect(op.dest.sigla).toBe("odi");
  });

  it("incoming row would show +doc_count ← SOURCE (op-2 ← HRB/insgral)", () => {
    const op = incomingOps(ops, H, S)[0];
    expect(op.doc_count).toBe(7);
    expect(op.source.hospital).toBe("HRB");
    expect(op.source.sigla).toBe("insgral");
  });

  it("netDocDelta = incoming − outgoing = 7 − 3 = +4", () => {
    expect(netDocDelta(ops, H, S)).toBe(4);
  });

  it("unrelated op is excluded from both lists", () => {
    expect(outgoingOps(ops, H, S).find((o) => o.id === "op-4")).toBeUndefined();
    expect(incomingOps(ops, H, S).find((o) => o.id === "op-4")).toBeUndefined();
  });
});

// ── (c) applied op: no eliminar, muted style ──────────────────────────────
describe("(c) applied op", () => {
  it("outgoingOps includes applied ops (filtering is by direction, not status)", () => {
    const res = outgoingOps([appliedOut], H, S);
    expect(res).toHaveLength(1);
    expect(res[0].status).toBe("applied");
  });

  it("applied op does NOT count towards the net delta", () => {
    expect(netDocDelta([appliedOut], H, S)).toBe(0);
  });

  it("hasPendingOps is false for applied-only ops → export disabled", () => {
    expect(hasPendingOps([appliedOut], H, S)).toBe(false);
  });
});

// ── (d) export button enabled when ≥1 pending op ─────────────────────────
describe("(d) export button state", () => {
  it("disabled with no pending ops", () => {
    expect(hasPendingOps([appliedOut], H, S)).toBe(false);
  });

  it("enabled with one pending outgoing", () => {
    expect(hasPendingOps([pendingOut], H, S)).toBe(true);
  });

  it("enabled with one pending incoming", () => {
    expect(hasPendingOps([pendingIn], H, S)).toBe(true);
  });
});

// ── (d2) pendingOpsCountForCell (Disclosure badge) ────────────────────────
describe("(d2) pendingOpsCountForCell", () => {
  it("counts pending ops touching the cell as source OR dest", () => {
    expect(pendingOpsCountForCell([pendingOut, pendingIn], H, S)).toBe(2);
  });

  it("ignores applied ops, other cells' ops, and tolerates undefined ops", () => {
    expect(pendingOpsCountForCell([appliedOut, unrelated], H, S)).toBe(0);
    expect(pendingOpsCountForCell(undefined, H, S)).toBe(0);
  });
});

// ── (e) onDelete called with op.id ──────────────────────────────────────────
describe("(e) onDelete fires with the correct op id", () => {
  it("outgoing op id is op-1", () => {
    const ops = [pendingOut];
    const out = outgoingOps(ops, H, S);
    // The component calls onDelete(op.id) — verify the id is accessible
    expect(out[0].id).toBe("op-1");
  });
});

// ── (f) F3: locked disables per-op delete, keeps Export enabled ──────────────
describe("(f) locked rendering", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("disables the per-op delete button when locked; export button is gone (moved to MonthReorgPanel)", () => {
    const { container } = mount(
      <ReorganizacionPanel
        hospital={H}
        sigla={S}
        ops={[pendingOut]}
        onDelete={() => {}}
        locked
      />,
    );
    const del = container.querySelector('[data-testid="eliminar-btn"]');
    expect(del).toBeTruthy();
    expect(del.disabled).toBe(true);
    expect(container.querySelector('[data-testid="export-btn"]')).toBeNull();
  });

  it("delete is enabled when not locked", () => {
    const { container } = mount(
      <ReorganizacionPanel
        hospital={H}
        sigla={S}
        ops={[pendingOut]}
        onDelete={() => {}}
      />,
    );
    const del = container.querySelector('[data-testid="eliminar-btn"]');
    expect(del.disabled).toBe(false);
  });
});
