import { describe, expect, it } from "vitest";

import { computeWindow } from "./list-window";

describe("computeWindow", () => {
  it("at the top renders the first screenful + overscan, no top spacer", () => {
    const w = computeWindow(0, 400, 40, 1300, 8);
    expect(w.start).toBe(0);
    expect(w.topPad).toBe(0);
    expect(w.end).toBe(10 + 8); // 400/40 visibles + overscan
    expect(w.bottomPad).toBe((1300 - 18) * 40);
  });

  it("mid-scroll: spacers preserve the exact total height", () => {
    const total = 1300;
    const rowH = 40;
    const w = computeWindow(20000, 400, rowH, total, 8);
    expect(w.start).toBeGreaterThan(0);
    expect(w.end).toBeLessThan(total);
    const rendered = (w.end - w.start) * rowH;
    expect(w.topPad + rendered + w.bottomPad).toBe(total * rowH);
    // La ventana cubre el viewport pedido
    expect(w.topPad).toBeLessThanOrEqual(20000);
    expect(w.topPad + rendered).toBeGreaterThanOrEqual(20000 + 400);
  });

  it("at the bottom clamps end to total, no bottom spacer", () => {
    const w = computeWindow(1300 * 40 - 400, 400, 40, 1300, 8);
    expect(w.end).toBe(1300);
    expect(w.bottomPad).toBe(0);
  });

  it("small lists render whole with no spacers", () => {
    const w = computeWindow(0, 400, 40, 7, 8);
    expect(w).toEqual({ start: 0, end: 7, topPad: 0, bottomPad: 0 });
  });

  it("empty list is a no-op", () => {
    expect(computeWindow(0, 400, 40, 0)).toEqual({ start: 0, end: 0, topPad: 0, bottomPad: 0 });
  });
});
