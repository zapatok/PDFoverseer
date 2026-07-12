// @vitest-environment jsdom
//
// Track D, Chunk D3, Task 9 — keyboard range marking in the reorg viewer.
// `[` marks range start at the current page, `]` marks end, `Escape` clears,
// `Enter` triggers ReorgHud's existing "Crear operación" flow (same
// `canCreate` guard, same §A10 dest-defaults — no bypass). None of this
// exists outside `mode="reorg"`, and `focusIsInInput()` keeps it inert while
// the operator is typing in the HUD's own inputs (matches the pattern in
// ReorgHud.defaults.test.jsx / cellFiles.singleFetch.test.jsx).
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("../lib/api", () => ({
  api: {
    getCellFiles: vi.fn(async () => [{ name: "a.pdf", page_count: 5, effective_count: null, origin: "R1" }]),
    cellPdfUrl: vi.fn(() => "http://test/pdf"),
  },
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
// pdf.js worker setup (DOMMatrix etc., absent in jsdom) — stub the hooks that
// pull it in, same as cellFiles.singleFetch.test.jsx. `doc` is a truthy
// placeholder object: WorkerThumbnails (the single thumbnail rail since Task
// 10) only checks doc/pageCount truthiness before rendering its page-button
// list (Thumb rasterizes lazily behind IntersectionObserver, stubbed below),
// so a plain object is enough to get real page buttons instead of the
// aria-hidden empty aside.
vi.mock("../hooks/usePdfDocument", () => ({
  usePdfDocument: () => ({ doc: {}, error: null }),
}));
vi.mock("../hooks/useFitScale", () => ({
  useFitScale: () => ({ panelRef: { current: null }, fitScale: 1 }),
}));
vi.mock("./PdfPage", () => ({ PdfPage: () => null, releaseRenderCache: () => {} }));

import { WorkerCountViewer } from "./WorkerCountViewer";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// jsdom implements neither `scrollIntoView` (no layout engine) nor
// `IntersectionObserver` — both are used by the real thumbnail rail
// (WorkerThumbnails) once `doc` is truthy. Stub them so mounting the full
// viewer doesn't crash; scrolling/intersection behavior isn't under test here.
if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = () => {};
}
if (typeof window.IntersectionObserver === "undefined") {
  window.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

async function flush() {
  await act(async () => {});
}

function press(key) {
  act(() => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  });
}

function findButton(container, predicate) {
  return Array.from(container.querySelectorAll("button")).find((b) =>
    typeof predicate === "string" ? b.textContent === predicate : predicate(b),
  );
}

function clickPage(container, pageNumber) {
  const btn = container.querySelector(`aside button[aria-label^="Página ${pageNumber}"]`);
  expect(btn, `page ${pageNumber} thumbnail button should exist`).toBeTruthy();
  act(() => {
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

describe("Track D §4 — reorg viewer keyboard range marking", () => {
  beforeEach(() => {
    useSessionStore.setState({ session: null, pendingSaves: {} });
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("[ marks range start at the current page", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    press("[");

    expect(findButton(view.container, "Inicio: pág. 1")).toBeTruthy();
    view.unmount();
  });

  it("] marks range end at the current page", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    press("[");
    clickPage(view.container, 3);
    press("]");

    expect(findButton(view.container, "Inicio: pág. 1")).toBeTruthy();
    expect(findButton(view.container, "Fin: pág. 3")).toBeTruthy();
    expect(view.container.textContent).toContain("Páginas 1–3");
    view.unmount();
  });

  it("marking end before start out of order is still a valid range once normalized (no 'Rango inválido')", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    // page 1: mark end first
    press("]");
    clickPage(view.container, 4);
    // page 4: mark start (start(4) > end(1) — raw, out of order)
    press("[");

    expect(findButton(view.container, "Inicio: pág. 4")).toBeTruthy();
    expect(findButton(view.container, "Fin: pág. 1")).toBeTruthy();
    expect(view.container.textContent).not.toContain("Rango inválido");
    expect(view.container.textContent).toContain("Páginas 1–4");
    view.unmount();
  });

  it("Escape clears the marked range", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    press("[");
    clickPage(view.container, 3);
    press("]");
    expect(findButton(view.container, "Inicio: pág. 1")).toBeTruthy();

    press("Escape");

    expect(findButton(view.container, "Marcar inicio")).toBeTruthy();
    expect(findButton(view.container, "Marcar fin")).toBeTruthy();
    expect(findButton(view.container, "Inicio: pág. 1")).toBeFalsy();
    view.unmount();
  });

  it("Enter with a marked range but the (source-defaulted, §A10) destination unchanged does NOT create an op — the existing guard is not bypassed", async () => {
    const onCreateOp = vi.fn(async () => {});
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={onCreateOp} />,
    );
    await flush();

    press("[");
    clickPage(view.container, 3);
    press("]");
    expect(view.container.textContent).toContain("El destino debe ser diferente al origen.");

    press("Enter");
    await flush();

    expect(onCreateOp).not.toHaveBeenCalled();
    view.unmount();
  });

  it("Enter with a marked range and a valid (changed) destination confirms/creates the op — same flow as the 'Crear operación' button", async () => {
    const onCreateOp = vi.fn(async () => {});
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={onCreateOp} />,
    );
    await flush();

    press("[");
    clickPage(view.container, 3);
    press("]");

    // pick a different destino sigla via the select (mouse-equivalent, same
    // idiom as ReorgHud.defaults.test.jsx) so the destino≠origen guard clears.
    const destSiglaSelect = view.container.querySelectorAll("select")[2];
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
    act(() => {
      setter.call(destSiglaSelect, "art");
      destSiglaSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(view.container.textContent).not.toContain("El destino debe ser diferente al origen.");

    press("Enter");
    await flush();

    expect(onCreateOp).toHaveBeenCalledTimes(1);
    const opDraft = onCreateOp.mock.calls[0][0];
    expect(opDraft.op_type).toBe("extract_pages");
    expect(opDraft.source).toEqual({ file: "a.pdf", page_range: [1, 3] });
    expect(opDraft.dest).toEqual({ hospital: "HRB", sigla: "art" });

    // handleCreate clears the range on success — the HUD returns to its
    // unmarked state, ready for the next selection.
    expect(findButton(view.container, "Marcar inicio")).toBeTruthy();
    view.unmount();
  });

  it("in mode=\"worker\" the reorg shortcuts don't exist — [ ] Escape Enter are all inert (no ReorgHud, no crash)", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="worker" onCreateOp={vi.fn()} />,
    );
    await flush();

    // ReorgHud isn't rendered in worker mode at all.
    expect(findButton(view.container, "Marcar inicio")).toBeFalsy();

    press("[");
    press("]");
    press("Escape");
    press("Enter");

    // no crash, and the worker-mode HUD (a different "Atajos" legend) is the
    // one actually mounted.
    expect(view.container.textContent).toContain("Atajos");
    view.unmount();
  });

  it("Escape while a HUD <select> has focus does NOT wipe the marked range (close-dropdown gesture stays local)", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    press("[");
    clickPage(view.container, 3);
    press("]");
    expect(findButton(view.container, "Inicio: pág. 1")).toBeTruthy();
    expect(findButton(view.container, "Fin: pág. 3")).toBeTruthy();

    // Focus the opType <select> (the natural way Escape gets pressed here:
    // opening the dropdown and closing it) and press Escape on window.
    const opTypeSelect = view.container.querySelectorAll("select")[0];
    act(() => {
      opTypeSelect.focus();
    });
    press("Escape");

    expect(findButton(view.container, "Inicio: pág. 1")).toBeTruthy();
    expect(findButton(view.container, "Fin: pág. 3")).toBeTruthy();
    view.unmount();
  });

  it("focusIsInInput guards the reorg shortcuts: typing while a plain input has focus does not mark", async () => {
    const outsideInput = document.createElement("input");
    document.body.appendChild(outsideInput);
    outsideInput.focus();

    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    press("[");

    expect(findButton(view.container, "Marcar inicio")).toBeTruthy();
    expect(findButton(view.container, "Inicio: pág. 1")).toBeFalsy();

    view.unmount();
    outsideInput.remove();
  });
});
