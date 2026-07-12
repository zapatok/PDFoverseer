// @vitest-environment jsdom
//
// §A5 — ScanConfirmDialog renders the store's pendingScanConfirm breakdown
// and wires Confirmar/Cancelar to confirmScanOcr/cancelScanOcr. Follows the
// DOM-mount pattern of OverridePanel.test.jsx (react-dom/client + act, real
// Zustand store with setState, no testing-library).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("../lib/api", () => ({ api: {} }));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ScanConfirmDialog from "./ScanConfirmDialog";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

const confirmScanOcr = vi.fn();
const cancelScanOcr = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  useSessionStore.setState({ pendingScanConfirm: null, confirmScanOcr, cancelScanOcr });
});

afterEach(() => {
  document.body.innerHTML = "";
});

function findButton(label) {
  return Array.from(document.querySelectorAll("button")).find((b) => b.textContent === label);
}

describe("ScanConfirmDialog", () => {
  it("renders nothing when there is no pending confirm", () => {
    const view = mount(<ScanConfirmDialog />);
    expect(document.body.textContent).not.toContain("Confirmar escaneo OCR");
    view.unmount();
  });

  it("shows the breakdown (cells, PDFs, ETA) when a scan is pending confirmation", () => {
    useSessionStore.setState({
      pendingScanConfirm: { sessionId: "2026-04", cellPairs: [["HPV", "art"]], totalPdfs: 120, mins: 2 },
    });
    const view = mount(<ScanConfirmDialog />);
    expect(document.body.textContent).toContain("Confirmar escaneo OCR");
    expect(document.body.textContent).toContain("120");
    expect(document.body.textContent).toContain("1 celda");
    expect(document.body.textContent).toContain("~2 min");
    view.unmount();
  });

  it("Confirmar calls confirmScanOcr", () => {
    useSessionStore.setState({
      pendingScanConfirm: { sessionId: "2026-04", cellPairs: [["HPV", "art"]], totalPdfs: 120, mins: 2 },
    });
    const view = mount(<ScanConfirmDialog />);
    const btn = findButton("Confirmar");
    expect(btn).toBeTruthy();
    act(() => btn.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(confirmScanOcr).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("Cancelar calls cancelScanOcr", () => {
    useSessionStore.setState({
      pendingScanConfirm: { sessionId: "2026-04", cellPairs: [["HPV", "art"]], totalPdfs: 120, mins: 2 },
    });
    const view = mount(<ScanConfirmDialog />);
    const btn = findButton("Cancelar");
    expect(btn).toBeTruthy();
    act(() => btn.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(cancelScanOcr).toHaveBeenCalledTimes(1);
    view.unmount();
  });
});
