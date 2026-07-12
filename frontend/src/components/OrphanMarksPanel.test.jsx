// @vitest-environment jsdom
//
// F1 (Task 2.4): the orphan worker-marks panel surfaces marks that belong to
// files no longer in the cell folder, offering migrate/discard. Follows the
// react-dom/client + act mount pattern (no testing-library in this project).
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from "sonner";
import OrphanMarksPanel from "./OrphanMarksPanel";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("OrphanMarksPanel", () => {
  it("lists each orphan file with its mark subtotal, a destination select, and both actions", () => {
    const cell = {
      worker_marks: { "gone.pdf": [{ page: 1, count: 7 }, { page: 3, count: 5 }] },
    };
    const { container } = mount(
      <OrphanMarksPanel
        hospital="HLL"
        sigla="charla"
        cell={cell}
        files={["real.pdf"]}
        sessionId="2026-04"
      />,
    );
    const text = container.textContent;
    expect(text).toContain("gone.pdf");
    expect(text).toContain("12 marcas"); // subtotal 7 + 5
    // destination <select> lists the present file
    const options = [...container.querySelectorAll("option")].map((o) => o.value);
    expect(options).toContain("real.pdf");
    expect(text).toContain("Migrar");
    expect(text).toContain("Descartar");
  });

  it("§A12: the discard-confirm Dialog's close button has an accessible name", () => {
    const cell = {
      worker_marks: { "gone.pdf": [{ page: 1, count: 7 }] },
    };
    const { container } = mount(
      <OrphanMarksPanel
        hospital="HLL"
        sigla="charla"
        cell={cell}
        files={["real.pdf"]}
        sessionId="2026-04"
      />,
    );
    const descartarBtn = [...container.querySelectorAll("button")].find(
      (b) => b.textContent === "Descartar",
    );
    act(() => descartarBtn.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    const closeBtn = document.querySelector('button[aria-label="Cerrar"]');
    expect(closeBtn).toBeTruthy();
  });

  it("renders null when there are no orphans (all marks belong to present files)", () => {
    const cell = { worker_marks: { "real.pdf": [{ page: 1, count: 3 }] } };
    const { container } = mount(
      <OrphanMarksPanel
        hospital="HLL"
        sigla="charla"
        cell={cell}
        files={["real.pdf"]}
        sessionId="2026-04"
      />,
    );
    expect(container.textContent).toBe("");
  });

  it("does NOT toast success when the store reports a handled 409 (returns null)", async () => {
    // F1 review fix: the store's 409 branch toasts the lock holder and returns
    // null; the panel must not fire toast.success on top of it.
    const reconcileMock = vi.fn(async () => null);
    useSessionStore.setState({ reconcileWorkerMarks: reconcileMock });
    const cell = { worker_marks: { "gone.pdf": [{ page: 1, count: 7 }] } };
    const { container } = mount(
      <OrphanMarksPanel
        hospital="HLL"
        sigla="charla"
        cell={cell}
        files={["real.pdf"]}
        sessionId="2026-04"
      />,
    );
    const migrar = [...container.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Migrar",
    );
    expect(migrar).toBeTruthy();
    await act(async () => {
      migrar.click();
    });
    expect(reconcileMock).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled(); // the store already toasted; the panel adds nothing
  });

  it("toasts success when the store returns the enriched cell (truthy)", async () => {
    const reconcileMock = vi.fn(async () => ({ worker_marks: {}, worker_count: 0 }));
    useSessionStore.setState({ reconcileWorkerMarks: reconcileMock });
    const cell = { worker_marks: { "gone.pdf": [{ page: 1, count: 7 }] } };
    const { container } = mount(
      <OrphanMarksPanel
        hospital="HLL"
        sigla="charla"
        cell={cell}
        files={["real.pdf"]}
        sessionId="2026-04"
      />,
    );
    const migrar = [...container.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Migrar",
    );
    await act(async () => {
      migrar.click();
    });
    expect(toast.success).toHaveBeenCalledTimes(1);
  });
});
