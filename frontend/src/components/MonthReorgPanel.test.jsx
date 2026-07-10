// @vitest-environment jsdom
//
// MonthReorgPanel (Task 18) — the ONE session-wide export surface. Groups
// PENDING reorg ops by their SOURCE cell (the op executes FROM the source
// file; a cross-cell op's dest renders inline via the reused OpRow). Applied
// ops are hidden entirely — they're already reflected in the counts, nothing
// left to export or delete. Follows the DOM-mount pattern of
// OverridePanel.test.jsx / DetailPanel.nearMatchNav.test.jsx (react-dom/client
// + act, no testing-library). Radix Dialog portals to document.body, not the
// local mount container, so assertions read document.body.
import { describe, it, expect, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import MonthReorgPanel from "./MonthReorgPanel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

const ops = [
  {
    id: "op_1",
    op_type: "rotate",
    status: "pending",
    rotation_deg: 90,
    source: { hospital: "HRB", sigla: "altura", file: "a.pdf" },
    dest: { hospital: "HRB", sigla: "altura" },
  },
  {
    id: "op_2",
    op_type: "move_file",
    status: "applied",
    doc_count: 2,
    source: { hospital: "HLU", sigla: "art", file: "b.pdf" },
    dest: { hospital: "HLU", sigla: "odi" },
  },
  // pending CROSS-CELL op — pins the grouping decision: groups by SOURCE.
  {
    id: "op_3",
    op_type: "extract_pages",
    status: "pending",
    doc_count: 21,
    source: { hospital: "HRB", sigla: "altura", file: "c.pdf", page_range: [80, 100] },
    dest: { hospital: "HRB", sigla: "insgral" },
  },
];

describe("MonthReorgPanel", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("groups pending ops by SOURCE cell and hides applied ones", () => {
    mount(
      <MonthReorgPanel open ops={ops} onClose={() => {}} onDelete={() => {}} onExport={() => {}} />,
    );
    expect(document.body.textContent).toContain("HRB · altura");
    expect(document.body.textContent).not.toContain("HLU · art");
  });

  it("a cross-cell op lists under its SOURCE cell, dest shown inline", () => {
    mount(
      <MonthReorgPanel open ops={ops} onClose={() => {}} onDelete={() => {}} onExport={() => {}} />,
    );
    const headers = [...document.querySelectorAll("h4")].map((h) => h.textContent);
    expect(headers.some((h) => h.includes("altura"))).toBe(true);
    expect(headers.some((h) => h.includes("insgral"))).toBe(false);
  });

  it("export button present and enabled with pending ops", () => {
    mount(
      <MonthReorgPanel open ops={ops} onClose={() => {}} onDelete={() => {}} onExport={() => {}} />,
    );
    const btn = document.querySelector('[data-testid="export-btn"]');
    expect(btn).toBeTruthy();
    expect(btn.disabled).toBe(false);
  });

  it("no pending ops → empty state + disabled export", () => {
    mount(
      <MonthReorgPanel
        open
        ops={[ops[1]]}
        onClose={() => {}}
        onDelete={() => {}}
        onExport={() => {}}
      />,
    );
    expect(document.body.textContent).toContain("Sin operaciones pendientes");
    const btn = document.querySelector('[data-testid="export-btn"]');
    expect(btn.disabled).toBe(true);
  });
});
