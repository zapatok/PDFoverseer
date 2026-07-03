import { describe, it, expect, vi, beforeEach } from "vitest";

// U6: `toast` from sonner is both callable (the neutral/default variant) and
// carries `.error`/`.success` methods — mirror the real API shape so a plain
// `toast(msg)` call (not `.error`/`.success`) works under test.
vi.mock("sonner", () => {
  const toastFn = vi.fn();
  toastFn.error = vi.fn();
  toastFn.success = vi.fn();
  return { toast: toastFn };
});

import { useSessionStore } from "./session";
import { toast } from "sonner";

describe("file_scan_error: cancelled vs real error (U6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSessionStore.setState({
      fileScan: {
        hospital: "HRB",
        sigla: "odi",
        filename: "a.pdf",
        page: 1,
        pagesTotal: 3,
        terminal: null,
      },
      error: null,
    });
  });

  it("a cancelled scan shows a neutral toast, not the sticky global error banner", () => {
    useSessionStore.getState()._handleWSEvent({
      type: "file_scan_error",
      hospital: "HRB",
      sigla: "odi",
      filename: "a.pdf",
      error: "cancelled",
    });

    expect(toast).toHaveBeenCalledWith("Escaneo cancelado");
    expect(toast.error).not.toHaveBeenCalled();

    const state = useSessionStore.getState();
    expect(state.error).toBeNull();
    expect(state.fileScan.terminal).toBe("cancelled");
  });

  it("a real scan error still sets the sticky global error (unchanged behavior)", () => {
    useSessionStore.getState()._handleWSEvent({
      type: "file_scan_error",
      hospital: "HRB",
      sigla: "odi",
      filename: "a.pdf",
      error: "boom",
    });

    expect(toast).not.toHaveBeenCalled();

    const state = useSessionStore.getState();
    expect(state.error).toBe("boom");
    expect(state.fileScan.terminal).toBe("error");
  });
});
