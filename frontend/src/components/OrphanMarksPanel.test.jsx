// @vitest-environment jsdom
//
// F1 (Task 2.4): the orphan worker-marks panel surfaces marks that belong to
// files no longer in the cell folder, offering migrate/discard. Follows the
// react-dom/client + act mount pattern (no testing-library in this project).
import { describe, it, expect, afterEach, vi } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import OrphanMarksPanel from "./OrphanMarksPanel";

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
});
