// @vitest-environment jsdom
//
// Track D, Chunk D3, Task 10 — pages inside the marked reorg range carry the
// po-override-* tint in the (real, unmocked) WorkerThumbnails rail. Uses the
// same truthy-`doc` + jsdom polyfill idiom as WorkerCountViewer.reorgKeys.test.jsx
// (ReorgThumbnails — soon WorkerThumbnails too — only checks doc truthiness,
// never calls a pdf.js method on it).
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

function pageButton(container, pageNumber) {
  return container.querySelector(`aside button[aria-label^="Página ${pageNumber}"]`);
}

function clickPage(container, pageNumber) {
  const btn = pageButton(container, pageNumber);
  expect(btn, `page ${pageNumber} thumbnail button should exist`).toBeTruthy();
  act(() => {
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

describe("Track D §4 Task 10 — reorg range tint on the real thumbnail rail", () => {
  beforeEach(() => {
    useSessionStore.setState({ session: null, pendingSaves: {} });
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("pages inside the marked range [1,3] carry the po-override tint; pages outside do not", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    press("[");           // start = 1 (current page)
    clickPage(view.container, 3);
    press("]");            // end = 3
    // Move the current page OUTSIDE the marked range so the tint assertion
    // below isn't conflated with the (separately-tested) active/current-page
    // ring, which visually takes precedence over the tint.
    clickPage(view.container, 5);
    await flush();

    const btn1 = pageButton(view.container, 1);
    const btn2 = pageButton(view.container, 2);
    const btn3 = pageButton(view.container, 3);
    const btn4 = pageButton(view.container, 4);
    const btn5 = pageButton(view.container, 5);

    for (const btn of [btn1, btn2, btn3]) {
      expect(btn.className).toContain("po-override");
    }
    for (const btn of [btn4]) {
      expect(btn.className).not.toContain("po-override");
    }
    // page 5 is both the current page AND outside the range — the accent
    // ring (active) wins visually, same precedence the old ReorgThumbnails
    // placeholder used (active > inRange > default).
    expect(btn5.className).toContain("po-accent");
    expect(btn5.className).not.toContain("po-override");
    view.unmount();
  });

  it("the active/current page shows the accent ring, not the tint, even when it is inside the marked range (active wins)", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    press("[");           // start = 1 (current page)
    clickPage(view.container, 3);
    press("]");            // end = 3, current page stays 3 (inside [1,3])
    await flush();

    const btn3 = pageButton(view.container, 3);
    expect(btn3.className).toContain("po-accent");
    expect(btn3.className).not.toContain("po-override");
    view.unmount();
  });

  it("no range marked: nothing carries the tint", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    for (let p = 1; p <= 5; p++) {
      expect(pageButton(view.container, p).className).not.toContain("po-override");
    }
    view.unmount();
  });

  it("worker mode never carries the reorg tint even if a doc has pages", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="worker" onCreateOp={vi.fn()} />,
    );
    await flush();

    for (let p = 1; p <= 5; p++) {
      const btn = pageButton(view.container, p);
      expect(btn, `page ${p} thumbnail button should exist`).toBeTruthy();
      expect(btn.className).not.toContain("po-override");
    }
    view.unmount();
  });
});
