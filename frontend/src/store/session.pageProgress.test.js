// @vitest-environment jsdom
// §C3 — pins the pdf_page_progress reducer: "pág. X/Y" detail inside the PDF
// currently being scanned (page/pagesTotal/pageCell), and its reset to null
// on the NEXT pdf_progress (a new PDF started — the finished PDF's page
// detail must not linger).
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({ session_id: "2026-04", cells: {} })),
    createSession: vi.fn(async () => ({})),
    listMonths: vi.fn(async () => ({ months: [] })),
    presenceHeartbeat: vi.fn(async () => ({ participants: [] })),
    presenceFocus: vi.fn(async () => ({})),
    presenceLeave: vi.fn(async () => ({})),
    beaconLeave: vi.fn(),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useSessionStore } from "./session";

const getState = () => useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState({
    session: { session_id: "2026-04", cells: {} },
    scanProgress: { done: 2, total: 5, unit: "pdf" },
  });
});

describe("pdf_page_progress reducer (§C3)", () => {
  it("sets page/pagesTotal/pageCell on the in-flight PDF", () => {
    getState()._handleWSEvent({
      type: "pdf_page_progress",
      hospital: "HRB",
      sigla: "odi",
      page: 3,
      pages_total: 12,
    });
    const sp = getState().scanProgress;
    expect(sp.page).toBe(3);
    expect(sp.pagesTotal).toBe(12);
    expect(sp.pageCell).toBe("HRB|odi");
  });

  it("does not clobber the surrounding scanProgress fields (done/total/unit)", () => {
    getState()._handleWSEvent({
      type: "pdf_page_progress",
      hospital: "HRB",
      sigla: "odi",
      page: 1,
      pages_total: 4,
    });
    const sp = getState().scanProgress;
    expect(sp.done).toBe(2);
    expect(sp.total).toBe(5);
    expect(sp.unit).toBe("pdf");
  });

  it("a later pdf_page_progress on a different cell overwrites page/pagesTotal/pageCell", () => {
    getState()._handleWSEvent({
      type: "pdf_page_progress",
      hospital: "HRB",
      sigla: "odi",
      page: 3,
      pages_total: 12,
    });
    getState()._handleWSEvent({
      type: "pdf_page_progress",
      hospital: "HPV",
      sigla: "art",
      page: 1,
      pages_total: 8,
    });
    const sp = getState().scanProgress;
    expect(sp.page).toBe(1);
    expect(sp.pagesTotal).toBe(8);
    expect(sp.pageCell).toBe("HPV|art");
  });

  it("the NEXT pdf_progress resets page/pagesTotal to null (the finished PDF's detail must not linger)", () => {
    getState()._handleWSEvent({
      type: "pdf_page_progress",
      hospital: "HRB",
      sigla: "odi",
      page: 3,
      pages_total: 12,
    });
    getState()._handleWSEvent({
      type: "pdf_progress",
      done: 3,
      total: 5,
      pdf_name: "big.pdf",
      eta_ms: 1200,
    });
    const sp = getState().scanProgress;
    expect(sp.page).toBeNull();
    expect(sp.pagesTotal).toBeNull();
    expect(sp.done).toBe(3);
    expect(sp.total).toBe(5);
    expect(sp.pdfName).toBe("big.pdf");
  });
});
