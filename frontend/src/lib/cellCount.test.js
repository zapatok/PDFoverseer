import { describe, expect, it } from "vitest";

import { _sumMarks, computeCellCount, computeFilesCount } from "./cellCount";

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

describe("_sumMarks — check tally helper", () => {
  it("sums only marks for present files, discards orphans", () => {
    const cell = {
      worker_marks: {
        "m.pdf": [{ page: 1, count: 5 }],
        "orphan.pdf": [{ page: 1, count: 9 }],
      },
    };
    expect(_sumMarks(cell, ["m.pdf"])).toBe(5);
  });

  it("empty presentFiles set returns 0", () => {
    const cell = { worker_marks: { "m.pdf": [{ page: 1, count: 5 }] } };
    expect(_sumMarks(cell, [])).toBe(0);
  });

  it("null presentFiles falls back to per_file filter (legacy)", () => {
    const cell = {
      worker_marks: {
        "a.pdf": [{ page: 1, count: 10 }],
        "b.pdf": [{ page: 1, count: 36 }],
      },
      per_file: { "a.pdf": 1 },
    };
    expect(_sumMarks(cell, null)).toBe(10); // b.pdf not in per_file
  });

  it("null presentFiles with empty per_file sums all marks", () => {
    const cell = {
      worker_marks: {
        "a.pdf": [{ page: 1, count: 10 }],
        "b.pdf": [{ page: 1, count: 5 }],
      },
    };
    expect(_sumMarks(cell, null)).toBe(15);
  });

  it("sums across multiple files and pages", () => {
    const cell = {
      worker_marks: {
        "a.pdf": [
          { page: 1, count: 3 },
          { page: 2, count: 4 },
        ],
        "b.pdf": [{ page: 1, count: 7 }],
        "c.pdf": [{ page: 1, count: 100 }],
      },
    };
    expect(_sumMarks(cell, ["a.pdf", "b.pdf"])).toBe(14);
  });

  it("no worker_marks returns 0", () => {
    expect(_sumMarks({}, ["m.pdf"])).toBe(0);
    expect(_sumMarks(null, ["m.pdf"])).toBe(0);
  });
});

describe("computeCellCount with count_type='checks'", () => {
  it("uses _sumMarks when count_type is checks", () => {
    const cell = {
      worker_marks: {
        "m.pdf": [{ page: 1, count: 5 }],
        "orphan.pdf": [{ page: 1, count: 9 }],
      },
    };
    expect(computeCellCount(cell, "checks", ["m.pdf"])).toBe(5);
  });

  it("user_override still wins for checks", () => {
    const cell = {
      worker_marks: { "m.pdf": [{ page: 1, count: 5 }] },
      user_override: 2,
    };
    expect(computeCellCount(cell, "checks", ["m.pdf"])).toBe(2);
  });

  it("documents type (default) ignores worker_marks", () => {
    const cell = {
      per_file: { "a.pdf": 3 },
      worker_marks: { "a.pdf": [{ page: 1, count: 99 }] },
    };
    expect(computeCellCount(cell)).toBe(3);
    expect(computeCellCount(cell, "documents")).toBe(3);
  });
});
