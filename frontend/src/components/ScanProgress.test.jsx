// @vitest-environment jsdom
// §C3 — pins the "pág. X/Y" in-flight page detail (pdf_page_progress): visible
// while page/pagesTotal are set and the scan is not terminal, absent once the
// next pdf_progress resets them to null. Follows the DOM-mount pattern of
// CategoryRow.test.jsx / HospitalCard.test.jsx (react-dom/client + act, real
// Zustand store seeded via setState).
import { describe, it, expect, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

import ScanProgress from "./ScanProgress";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("ScanProgress — pdf_page_progress detail (§C3)", () => {
  it('shows "pág. X/Y" when scanProgress carries page/pagesTotal', () => {
    useSessionStore.setState({
      session: { session_id: "2026-04", cells: {} },
      scanProgress: { done: 1, total: 5, unit: "pdf", page: 3, pagesTotal: 12 },
    });
    const { container, unmount } = mount(<ScanProgress />);
    expect(container.textContent).toContain("pág. 3/12");
    unmount();
  });

  it("does not show the page detail once page/pagesTotal are reset to null", () => {
    useSessionStore.setState({
      session: { session_id: "2026-04", cells: {} },
      scanProgress: {
        done: 3,
        total: 5,
        unit: "pdf",
        page: null,
        pagesTotal: null,
        pdfName: "big.pdf",
      },
    });
    const { container, unmount } = mount(<ScanProgress />);
    expect(container.textContent).not.toContain("pág.");
    unmount();
  });

  it("does not show the page detail once the scan is terminal, even if page/pagesTotal linger", () => {
    useSessionStore.setState({
      session: { session_id: "2026-04", cells: {} },
      scanProgress: {
        done: 5,
        total: 5,
        unit: "pdf",
        page: 3,
        pagesTotal: 12,
        terminal: "complete",
        skipped: [],
      },
    });
    const { container, unmount } = mount(<ScanProgress />);
    expect(container.textContent).not.toContain("pág.");
    unmount();
  });

  it("renders nothing when there is no scanProgress at all", () => {
    useSessionStore.setState({
      session: { session_id: "2026-04", cells: {} },
      scanProgress: null,
    });
    const { container, unmount } = mount(<ScanProgress />);
    expect(container.innerHTML).toBe("");
    unmount();
  });
});
