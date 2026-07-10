// @vitest-environment jsdom
//
// Wiring test for the render-cache teardown: usePdfDocument's cleanup must
// call releaseRenderCache(doc) BEFORE destroying the pdf.js doc, so the LRU's
// ImageBitmaps close deterministically instead of waiting for GC when the
// operator flips through files. The function body itself is 2 lines over the
// already-tested LruCache.clear() — this test asserts the hook calls it.
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

const { fakeDoc, getDocument, releaseRenderCache } = vi.hoisted(() => ({
  fakeDoc: { numPages: 3, destroy: vi.fn() },
  getDocument: vi.fn(),
  releaseRenderCache: vi.fn(),
}));

// El hook importa ../lib/pdf (setup del worker de pdfjs-dist) — stub para que
// el mount en jsdom quede liviano, igual que en DetailPanel.reorgLoop.test.jsx.
vi.mock("../lib/pdf", () => ({ pdfjsLib: { getDocument } }));
vi.mock("../components/PdfPage", () => ({ releaseRenderCache }));

import { usePdfDocument } from "./usePdfDocument";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function Probe({ url }) {
  usePdfDocument(url);
  return null;
}

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { unmount: () => act(() => root.unmount()) };
}

describe("usePdfDocument — render-cache teardown", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("cleanup releases the loaded doc's render cache before destroying it", async () => {
    getDocument.mockReturnValue({
      promise: Promise.resolve(fakeDoc),
      destroy: vi.fn(),
    });
    const view = mount(<Probe url="/fake.pdf" />);
    await act(async () => {}); // deja resolver getDocument → setDoc(pdf)
    view.unmount();
    expect(releaseRenderCache).toHaveBeenCalledWith(fakeDoc);
  });

  it("does NOT release when the doc never finished loading", () => {
    getDocument.mockReturnValue({
      promise: new Promise(() => {}), // nunca resuelve
      destroy: vi.fn(),
    });
    const view = mount(<Probe url="/fake.pdf" />);
    view.unmount();
    expect(releaseRenderCache).not.toHaveBeenCalled();
  });
});
