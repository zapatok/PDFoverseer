// @vitest-environment jsdom
//
// U4: the per-sigla dot tooltip must show the SAME number as the rest of the
// app (computeCellCount — user_override > per_file_overrides ∪ per_file >
// ocr_count > filename_count, additive reorg_doc_delta), not the older ad-hoc
// `user_override ?? ocr_count ?? filename_count ?? 0` cascade, which ignored
// per-file overrides and reorg deltas entirely and could show a stale 0.
import { describe, it, expect, afterEach, vi } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

// Sidestep Radix's hover/portal machinery (delayDuration + a Provider live in
// App.jsx) — assert on the computed content string the real Tooltip would
// receive, not the interactive popup.
vi.mock("../ui/Tooltip", () => ({
  default: ({ content, children }) => (
    <div data-testid="tooltip" data-content={content}>
      {children}
    </div>
  ),
}));

import HospitalCard from "./HospitalCard";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

describe("HospitalCard — per-sigla dot tooltip is honest (U4)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("reads the computeCellCount total (per-file overrides + reorg delta), not the stale cascade", () => {
    const cells = {
      odi: {
        per_file: { "a.pdf": 2 },
        per_file_overrides: { "a.pdf": 5 },
        reorg_doc_delta: 1,
      },
    };
    const { container } = mount(
      <HospitalCard hospital="HPV" total={6} cells={cells} status="ok" onClick={() => {}} />,
    );
    const tooltips = container.querySelectorAll('[data-testid="tooltip"]');
    const odiTooltip = Array.from(tooltips).find((el) =>
      el.getAttribute("data-content").startsWith("odi: "),
    );
    expect(odiTooltip).toBeTruthy();
    // per_file_overrides["a.pdf"]=5 wins over per_file["a.pdf"]=2, + reorg_doc_delta 1 = 6.
    // The stale cascade (user_override ?? ocr_count ?? filename_count ?? 0) would show 0.
    expect(odiTooltip.getAttribute("data-content")).toBe("odi: 6");
  });
});
