// @vitest-environment jsdom
// §A5 — the OCR cost guard drops window.confirm (blocks the thread, can't
// show a breakdown) for an in-app confirm gated on the store's own
// pendingScanConfirm state, rendered by ScanConfirmDialog. scanOcr itself is
// the trigger; confirmScanOcr/cancelScanOcr resolve it.
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    scanOcr: vi.fn(async () => ({ total_pdfs: 5 })),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useSessionStore } from "./session";
import { api } from "../lib/api";
import { setIdentity } from "../lib/identity";
import { OCR_CONFIRM_PDF_THRESHOLD } from "../lib/constants";

const getState = () => useSessionStore.getState();

function seed(filenameCount) {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: { HPV: { art: { filename_count: filenameCount } } },
    },
    pendingScanConfirm: null,
  });
}

beforeEach(() => {
  localStorage.clear();
  setIdentity({ name: "Daniel", color: "#ef4444" });
  vi.clearAllMocks();
});

describe("scanOcr under the threshold", () => {
  it("launches directly — no confirm, no pendingScanConfirm", async () => {
    seed(OCR_CONFIRM_PDF_THRESHOLD - 1);
    await getState().scanOcr("2026-04", [["HPV", "art"]]);
    expect(api.scanOcr).toHaveBeenCalledTimes(1);
    expect(getState().pendingScanConfirm).toBeNull();
    expect(getState().scanProgress).toEqual({ done: 0, total: 5, unit: "pdf" });
  });
});

describe("scanOcr over the threshold", () => {
  it("sets pendingScanConfirm and does NOT call api.scanOcr", async () => {
    seed(OCR_CONFIRM_PDF_THRESHOLD + 1);
    await getState().scanOcr("2026-04", [["HPV", "art"]]);
    expect(api.scanOcr).not.toHaveBeenCalled();
    const pending = getState().pendingScanConfirm;
    expect(pending).not.toBeNull();
    expect(pending.sessionId).toBe("2026-04");
    expect(pending.cellPairs).toEqual([["HPV", "art"]]);
    expect(pending.totalPdfs).toBe(OCR_CONFIRM_PDF_THRESHOLD + 1);
    expect(pending.mins).toBeGreaterThan(0);
  });

  it("Confirmar launches api.scanOcr with the same pairs + participant_id, and clears pendingScanConfirm", async () => {
    seed(OCR_CONFIRM_PDF_THRESHOLD + 1);
    await getState().scanOcr("2026-04", [["HPV", "art"]]);
    expect(api.scanOcr).not.toHaveBeenCalled();
    await getState().confirmScanOcr();
    expect(api.scanOcr).toHaveBeenCalledTimes(1);
    expect(api.scanOcr).toHaveBeenCalledWith("2026-04", [["HPV", "art"]], expect.any(String));
    expect(getState().pendingScanConfirm).toBeNull();
    expect(getState().scanProgress).toEqual({ done: 0, total: 5, unit: "pdf" });
  });

  it("Cancelar clears pendingScanConfirm without ever calling api.scanOcr", async () => {
    seed(OCR_CONFIRM_PDF_THRESHOLD + 1);
    await getState().scanOcr("2026-04", [["HPV", "art"]]);
    getState().cancelScanOcr();
    expect(getState().pendingScanConfirm).toBeNull();
    expect(api.scanOcr).not.toHaveBeenCalled();
  });
});
