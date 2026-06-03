import { describe, it, expect, beforeEach } from "vitest";

import { useSessionStore } from "./session";

describe("per-PDF scan progress (audit #1)", () => {
  beforeEach(() => {
    useSessionStore.setState({ scanProgress: null, scanningCells: new Set() });
  });

  it("scan_started sizes the bar from total_pdfs", () => {
    useSessionStore
      .getState()
      ._handleWSEvent({ type: "scan_started", total_pdfs: 5, total_cells: 2 });
    const sp = useSessionStore.getState().scanProgress;
    expect(sp.done).toBe(0);
    expect(sp.total).toBe(5);
    expect(sp.unit).toBe("pdf");
  });

  it("pdf_progress updates done/total/pdfName/etaMs", () => {
    const { _handleWSEvent } = useSessionStore.getState();
    _handleWSEvent({ type: "scan_started", total_pdfs: 5, total_cells: 2 });
    _handleWSEvent({
      type: "pdf_progress",
      done: 2,
      total: 5,
      pdf_name: "x.pdf",
      eta_ms: 9000,
    });
    const sp = useSessionStore.getState().scanProgress;
    expect(sp.done).toBe(2);
    expect(sp.total).toBe(5);
    expect(sp.pdfName).toBe("x.pdf");
    expect(sp.etaMs).toBe(9000);
  });

  it("scan_complete finalizes at 100% without clobbering the PDF total", () => {
    const { _handleWSEvent } = useSessionStore.getState();
    _handleWSEvent({ type: "scan_started", total_pdfs: 5, total_cells: 2 });
    _handleWSEvent({ type: "pdf_progress", done: 4, total: 5, pdf_name: "d.pdf", eta_ms: 1000 });
    _handleWSEvent({ type: "scan_complete", scanned: 2, errors: 0, cancelled: 0 });
    const sp = useSessionStore.getState().scanProgress;
    expect(sp.terminal).toBe("complete");
    expect(sp.total).toBe(5);
    expect(sp.done).toBe(5);
  });

  it("legacy scan_progress (cell granularity) does not clobber the PDF bar", () => {
    const { _handleWSEvent } = useSessionStore.getState();
    _handleWSEvent({ type: "scan_started", total_pdfs: 50, total_cells: 1 });
    _handleWSEvent({ type: "pdf_progress", done: 10, total: 50, pdf_name: "p.pdf", eta_ms: 5000 });
    _handleWSEvent({ type: "scan_progress", done: 1, total: 1 });
    const sp = useSessionStore.getState().scanProgress;
    expect(sp.total).toBe(50);
    expect(sp.done).toBe(10);
  });
});
