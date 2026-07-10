// @vitest-environment jsdom
//
// Near-match viewer nav (Chunk 4 fast-follow): the viewer must track the
// ACTIVE ITEM'S IDENTITY (pdf_name + page_index), not its list position.
// The store's cell_updated WS handler wholesale-replaces the cell (incl.
// near_matches) on ANY remote write — another participant's clearNearMatches
// or a background scan finishing. With a positional viewerIndex, removing an
// item EARLIER in the list silently swapped the open viewer to a different,
// still-valid candidate (nothing looked broken). These tests simulate the
// remote replacement by re-rendering DetailPanel with a new cell prop.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import * as RadixTooltip from "@radix-ui/react-tooltip";

// Capture the viewer's props (for onNext/onPrev) and render an observable,
// viewer-only marker string — row text also contains pdf_names, so assertions
// key on the "VIEWER " prefix that only this mock emits.
const viewer = vi.hoisted(() => ({ props: null }));
vi.mock("./PdfCoverViewer", () => ({
  default: (props) => {
    viewer.props = props;
    return <div>{`VIEWER ${props.title} · ${props.positionLabel}`}</div>;
  },
}));
vi.mock("../lib/api", () => ({
  api: {
    getScanInfo: vi.fn(async () => ({ count_type: "documents", kind: "none" })),
    getCellFiles: vi.fn(async () => []),
    // Non-empty: an empty string is falsy and would keep the viewer unrendered.
    cellPdfUrl: vi.fn(() => "http://test/pdf"),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import DetailPanel from "./DetailPanel";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const NM = (n) => ({
  pdf_name: `doc${n}.pdf`,
  page_index: n,
  flavor_name: `flavor-${n}`,
  matched_anchors: ["a1"],
  missing_anchors: [],
});

// per_file always carries ALL names (a remote near-match clear doesn't remove
// files from disk), so `located` stays true for every surviving candidate.
function makeCell(nearMatches, allNames) {
  return {
    filename_count: allNames.length,
    per_file: Object.fromEntries(allNames.map((name) => [name, { count: 1 }])),
    near_matches: nearMatches,
    flags: [],
  };
}

// DetailPanel renders ui/Tooltip, whose Radix root requires the provider that
// App.jsx normally supplies — mirror it here.
function withProvider(ui) {
  return <RadixTooltip.Provider delayDuration={300}>{ui}</RadixTooltip.Provider>;
}

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(withProvider(ui)));
  return {
    container,
    rerender: (next) => act(() => root.render(withProvider(next))),
    unmount: () => act(() => root.unmount()),
  };
}

async function flush() {
  await act(async () => {});
}

function clickVerPortada(container, i) {
  const buttons = [...container.querySelectorAll("button")].filter((b) =>
    b.textContent.includes("Ver portada"),
  );
  act(() => buttons[i].dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

describe("DetailPanel — near-match viewer tracks identity, not position", () => {
  beforeEach(() => {
    viewer.props = null;
    useSessionStore.setState({
      session: { session_id: "2026-06", cells: {} },
      filesTick: {},
      presence: [],
    });
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("(a) opens row i and onNext steps to i+1", async () => {
    const items = [NM(0), NM(1), NM(2)];
    const allNames = items.map((x) => x.pdf_name);
    const view = mount(
      <DetailPanel hospital="HRB" sigla="odi" cell={makeCell(items, allNames)} />,
    );
    await flush();

    clickVerPortada(view.container, 0);
    expect(document.body.textContent).toContain("VIEWER doc0.pdf — p. 1 · 1 de 3");
    expect(viewer.props.onPrev).toBeNull(); // first item: no prev

    act(() => viewer.props.onNext());
    expect(document.body.textContent).toContain("VIEWER doc1.pdf — p. 2 · 2 de 3");
    expect(viewer.props.onPrev).not.toBeNull();
    expect(viewer.props.onNext).not.toBeNull();

    view.unmount();
  });

  it("(b) removing an EARLIER item keeps the viewer on the SAME identity", async () => {
    const items = [NM(0), NM(1), NM(2), NM(3), NM(4)];
    const allNames = items.map((x) => x.pdf_name);
    const view = mount(
      <DetailPanel hospital="HRB" sigla="odi" cell={makeCell(items, allNames)} />,
    );
    await flush();

    clickVerPortada(view.container, 2);
    expect(document.body.textContent).toContain("VIEWER doc2.pdf — p. 3 · 3 de 5");

    // Remote cell_updated: someone discarded item 0 → the list shifts left.
    view.rerender(
      <DetailPanel hospital="HRB" sigla="odi" cell={makeCell(items.slice(1), allNames)} />,
    );
    expect(document.body.textContent).toContain("VIEWER doc2.pdf — p. 3 · 2 de 4");

    view.unmount();
  });

  it("(c) removing the VIEWED item closes the viewer", async () => {
    const items = [NM(0), NM(1), NM(2)];
    const allNames = items.map((x) => x.pdf_name);
    const view = mount(
      <DetailPanel hospital="HRB" sigla="odi" cell={makeCell(items, allNames)} />,
    );
    await flush();

    clickVerPortada(view.container, 1);
    expect(document.body.textContent).toContain("VIEWER doc1.pdf — p. 2 · 2 de 3");

    // Remote cell_updated: the viewed candidate itself was discarded.
    view.rerender(
      <DetailPanel
        hospital="HRB"
        sigla="odi"
        cell={makeCell([items[0], items[2]], allNames)}
      />,
    );
    expect(document.body.textContent).not.toContain("VIEWER");

    view.unmount();
  });

  it("(d) hospital change resets the viewer even if the identity survives", async () => {
    const items = [NM(0), NM(1), NM(2)];
    const allNames = items.map((x) => x.pdf_name);
    const cell = makeCell(items, allNames);
    const view = mount(<DetailPanel hospital="HRB" sigla="odi" cell={cell} />);
    await flush();

    clickVerPortada(view.container, 0);
    expect(document.body.textContent).toContain("VIEWER doc0.pdf — p. 1 · 1 de 3");

    // Same near_matches in the new cell: only the explicit cell-switch reset
    // (not the identity-gone close) can close the viewer here.
    view.rerender(<DetailPanel hospital="HPV" sigla="odi" cell={cell} />);
    await flush();
    expect(document.body.textContent).not.toContain("VIEWER");

    view.unmount();
  });
});
