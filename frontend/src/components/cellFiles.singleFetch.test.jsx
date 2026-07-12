// @vitest-environment jsdom
//
// §A1 AC(1) — the literal acceptance scenario: with FileList + DetailPanel +
// PDFLightbox ALL mounted on the same cell, one filesTick bump produces
// exactly ONE api.getCellFiles call (the store's fetchCellFiles), not three.
// Before A1 each consumer ran its own tick-keyed fetch effect → 2-3 identical
// GETs per save; this pins the centralization. Radix Dialog portals to
// document.body (MonthReorgPanel.test.jsx pattern).
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import * as RadixTooltip from "@radix-ui/react-tooltip";

vi.mock("../lib/api", () => ({
  api: {
    getCellFiles: vi.fn(async () => [{ name: "a.pdf", page_count: 3, effective_count: 1, origin: "R1" }]),
    getScanInfo: vi.fn(async () => ({ count_type: "documents", kind: "filename_glob" })),
    cellPdfUrl: vi.fn(() => "http://test/pdf"),
  },
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
// PDFLightbox's pdf.js stack (pdfjs-dist worker setup at import time) — stub
// the heavy modules; the test only cares about fetch behavior, not rendering.
vi.mock("../hooks/usePdfDocument", () => ({
  usePdfDocument: () => ({ doc: null, numPages: 0, error: null, loading: true }),
}));
vi.mock("../hooks/useFitScale", () => ({
  useFitScale: () => ({ panelRef: { current: null }, fitScale: 1 }),
}));
vi.mock("./PdfPage", () => ({ PdfPage: () => null, releaseRenderCache: () => {} }));
vi.mock("./WorkerThumbnails", () => ({ WorkerThumbnails: () => null, getCachedThumb: () => null }));
vi.mock("./WorkerCountViewer", () => ({ WorkerCountViewer: () => null }));
vi.mock("./PdfCoverViewer", () => ({ default: () => null }));

import FileList from "./FileList";
import DetailPanel from "./DetailPanel";
import PDFLightbox from "./PDFLightbox";
import { api } from "../lib/api";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(<RadixTooltip.Provider delayDuration={300}>{ui}</RadixTooltip.Provider>));
  return { container, unmount: () => act(() => root.unmount()) };
}

async function flush() {
  await act(async () => {});
}

describe("§A1 AC(1) — un solo GET por bump con los 3 consumidores montados", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("FileList + DetailPanel + PDFLightbox montados: 0 fetches al montar, exactamente 1 por bump de tick", async () => {
    const cell = { filename_count: 1, per_file: { "a.pdf": 1 }, flags: [] };
    useSessionStore.setState({
      session: { session_id: "2026-06", cells: { HPV: { odi: cell } } },
      cellFiles: {
        "HPV|odi": {
          files: [{ name: "a.pdf", page_count: 3, effective_count: 1, origin: "R1" }],
          error: null,
        },
      },
      filesTick: {},
      presence: [],
      _pendingSave: new Map(),
      _cellFilesFetch: new Map(),
      lightbox: { hospital: "HPV", sigla: "odi", fileIndex: 0, mode: "inspect" },
    });

    const view = mount(
      <>
        <FileList hospital="HPV" sigla="odi" />
        <DetailPanel hospital="HPV" sigla="odi" cell={cell} />
        <PDFLightbox />
      </>,
    );
    await flush();

    // Ningún consumidor fetchea por su cuenta al montar (la entrada ya está
    // cacheada — el fetch del primer open lo dispara HospitalDetail, no ellos).
    expect(api.getCellFiles).toHaveBeenCalledTimes(0);

    // Un bump de tick (cell_updated es el camino real: cada save/broadcast
    // termina aquí) → UN solo GET para los tres consumidores.
    await act(async () => {
      useSessionStore.getState()._handleWSEvent({
        type: "cell_updated",
        hospital: "HPV",
        sigla: "odi",
        actor: null,
        cell: { ...cell, ocr_count: 1 },
      });
    });
    await flush();

    expect(api.getCellFiles).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().filesTick["HPV|odi"]).toBe(1);

    view.unmount();
  });
});
