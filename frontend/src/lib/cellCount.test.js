import { describe, expect, it } from "vitest";

import { computeCellCount, computeFilesCount } from "./cellCount";

describe("computeFilesCount (ignores user_override)", () => {
  it("sums per_file with per_file_overrides taking precedence", () => {
    const cell = {
      per_file: { "a.pdf": 1, "b.pdf": 2 },
      per_file_overrides: { "b.pdf": 5 },
    };
    expect(computeFilesCount(cell)).toBe(6); // 1 + 5
  });

  it("ignores user_override entirely", () => {
    const cell = { per_file: { "a.pdf": 3 }, user_override: 999 };
    expect(computeFilesCount(cell)).toBe(3);
  });

  it("falls back to ocr_count then filename_count then 0 when no per-file data", () => {
    expect(computeFilesCount({ ocr_count: 7 })).toBe(7);
    expect(computeFilesCount({ filename_count: 4 })).toBe(4);
    expect(computeFilesCount({})).toBe(0);
    expect(computeFilesCount(null)).toBe(0);
  });

  it("unions keys: an override for a file absent from per_file still counts", () => {
    const cell = {
      per_file: { "a.pdf": 1 },
      per_file_overrides: { "b.pdf": 4 }, // b.pdf not in per_file
    };
    expect(computeFilesCount(cell)).toBe(5); // 1 + 4
  });
});

describe("computeCellCount (override wins, else files)", () => {
  it("returns user_override when present (including 0)", () => {
    expect(computeCellCount({ per_file: { "a.pdf": 3 }, user_override: 10 })).toBe(10);
    expect(computeCellCount({ per_file: { "a.pdf": 3 }, user_override: 0 })).toBe(0);
  });

  it("equals computeFilesCount when no override (parity preserved)", () => {
    const cell = { per_file: { "a.pdf": 1, "b.pdf": 2 }, per_file_overrides: { "b.pdf": 5 } };
    expect(computeCellCount(cell)).toBe(computeFilesCount(cell));
  });
});
