// @vitest-environment jsdom
//
// Track D, Chunk D3, Task 10 — the reorg-mode thumbnail rail must go through
// the SAME lazy pipeline as worker-count mode (WorkerThumbnails: `Thumb` +
// `THUMB_CACHE` WeakMap + `getCachedThumb`), not a second, duplicated
// component. `./WorkerThumbnails` is mocked with a spy so this test doesn't
// need pdf.js/IntersectionObserver plumbing — it only proves ONE renderer is
// used in BOTH modes (mock the renderer, assert calls, per the plan).
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

const workerThumbnailsSpy = vi.fn(() => React.createElement("aside", { "data-testid": "worker-thumbnails-spy" }));
vi.mock("./WorkerThumbnails", () => ({
  WorkerThumbnails: (props) => workerThumbnailsSpy(props),
  getCachedThumb: () => null,
}));

import { WorkerCountViewer } from "./WorkerCountViewer";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

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

describe("Track D §4 Task 10 — reorg rail uses the SAME lazy thumbnail pipeline as worker mode", () => {
  beforeEach(() => {
    useSessionStore.setState({ session: null, pendingSaves: {} });
    workerThumbnailsSpy.mockClear();
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("mode=\"reorg\" renders through WorkerThumbnails (not a separate static placeholder)", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    expect(workerThumbnailsSpy).toHaveBeenCalled();
    const props = workerThumbnailsSpy.mock.calls.at(-1)[0];
    expect(props.pageCount).toBe(5);
    expect(props.currentPage).toBe(1);
    expect(typeof props.onSelect).toBe("function");
    // No standalone "…" placeholder text node anywhere — the old
    // ReorgThumbnails placeholder is gone, this is the real (mocked) renderer.
    expect(view.container.textContent).not.toContain("…");
    view.unmount();
  });

  it("mode=\"worker\" ALSO renders through the exact same WorkerThumbnails component (single pipeline, no duplication)", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="worker" onCreateOp={vi.fn()} />,
    );
    await flush();

    expect(workerThumbnailsSpy).toHaveBeenCalled();
    const props = workerThumbnailsSpy.mock.calls.at(-1)[0];
    expect(props.pageCount).toBe(5);
    view.unmount();
  });

  it("passes the marked range down to WorkerThumbnails in reorg mode", async () => {
    const view = mount(
      <WorkerCountViewer sessionId="2026-07" hospital="HRB" sigla="odi" mode="reorg" onCreateOp={vi.fn()} />,
    );
    await flush();

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "[", bubbles: true }));
    });
    await flush();

    const props = workerThumbnailsSpy.mock.calls.at(-1)[0];
    expect(props.reorgStart).toBe(1);
    view.unmount();
  });
});
