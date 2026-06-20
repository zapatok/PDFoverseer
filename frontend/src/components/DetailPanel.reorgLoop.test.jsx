// @vitest-environment jsdom
//
// Regression test for the MAYO "blank screen" bug (React #185 — "Maximum update
// depth exceeded"). Root cause: DetailPanel selected `s.session?.reorg_ops ?? []`
// INSIDE a Zustand v5 selector. When a session has no reorg_ops key (no reorg op
// was ever created — true for any pre-Incr-J month like MAYO), the `?? []` minted
// a fresh array reference every render, so the store read the snapshot as
// "changed" on every render → infinite render loop → blank screen.
//
// The fix selects the raw value (stable) and defaults OUTSIDE the selector. This
// test mounts DetailPanel against a MAYO-shaped session (reorg_ops absent) and
// asserts it renders the empty state without exceeding the update depth.
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

// PdfCoverViewer pulls pdfjs-dist (worker setup) at import time — stub it so the
// jsdom mount stays light. With sigla=null it never renders anyway.
vi.mock("./PdfCoverViewer", () => ({ default: () => null }));
vi.mock("../lib/api", () => ({
  api: {
    getScanInfo: vi.fn(async () => ({ count_type: "documents" })),
    getCellFiles: vi.fn(async () => []),
    cellPdfUrl: vi.fn(() => ""),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import DetailPanel from "./DetailPanel";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

describe("DetailPanel — no infinite render loop without reorg_ops (React #185)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("renders the empty state (sigla=null) on a MAYO-shaped session", () => {
    // MAYO from the API: reorg_ops / reorg_seq simply absent.
    useSessionStore.setState({
      session: { session_id: "2026-05", cells: {} },
      filesTick: {},
    });

    let view;
    expect(() => {
      view = mount(<DetailPanel hospital="HRB" sigla={null} cell={null} />);
    }).not.toThrow();

    expect(document.body.textContent).toContain("Selecciona una categoría");
    view.unmount();
  });
});
