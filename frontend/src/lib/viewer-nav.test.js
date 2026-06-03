import { describe, expect, it } from "vitest";

import { wheelToPageStep, WHEEL_PAGE_THRESHOLD } from "./viewer-nav";

describe("wheelToPageStep", () => {
  it("accumulates small deltas until threshold, then steps once", () => {
    let acc = 0;
    let step;
    ({ step, acc } = wheelToPageStep(WHEEL_PAGE_THRESHOLD / 2, acc));
    expect(step).toBe(0);
    ({ step, acc } = wheelToPageStep(WHEEL_PAGE_THRESHOLD / 2 + 1, acc));
    expect(step).toBe(1); // forward one page
    expect(acc).toBe(0); // resets after a step
  });

  it("steps -1 on sufficient negative delta", () => {
    const { step } = wheelToPageStep(-WHEEL_PAGE_THRESHOLD - 1, 0);
    expect(step).toBe(-1);
  });
});
