import { describe, it, expect } from "vitest";

import { estimateScanSeconds, formatEta, shouldConfirmScan, totalPdfsForPairs } from "./scanCost";

describe("formatEta", () => {
  it("rounds to whole minutes, min 1", () => {
    expect(formatEta(90_000)).toBe("~2 min"); // 1.5 min -> 2
    expect(formatEta(20_000)).toBe("~1 min"); // <1 min -> 1
    expect(formatEta(600_000)).toBe("~10 min");
  });
});

describe("scanCost", () => {
  it("confirms strictly above the threshold", () => {
    expect(shouldConfirmScan(60, 50)).toBe(true);
    expect(shouldConfirmScan(10, 50)).toBe(false);
    expect(shouldConfirmScan(50, 50)).toBe(false); // boundary: not >
  });

  it("estimates seconds from the per-PDF constant", () => {
    expect(estimateScanSeconds(10)).toBe(10); // §A5: recalibrated to 1 s/PDF
  });

  it("sums filename_count over the selected pairs", () => {
    const state = {
      cells: {
        HPV: { art: { filename_count: 767 } },
        HRB: { odi: { filename_count: 1 } },
      },
    };
    expect(
      totalPdfsForPairs(state, [
        ["HPV", "art"],
        ["HRB", "odi"],
      ])
    ).toBe(768);
  });

  it("falls back to the computed count when filename_count is missing", () => {
    const state = { cells: { HPV: { art: { user_override: 5 } } } };
    expect(totalPdfsForPairs(state, [["HPV", "art"]])).toBe(5);
  });

  it("ignores unknown pairs and tolerates empty state", () => {
    expect(totalPdfsForPairs({ cells: {} }, [["X", "y"]])).toBe(0);
    expect(totalPdfsForPairs(null, [["X", "y"]])).toBe(0);
    expect(totalPdfsForPairs({ cells: {} }, undefined)).toBe(0);
  });
});
