import { describe, it, expect } from "vitest";
import { pageRotation, rotationForPageFn } from "./page-rotation";

const op = (over = {}) => ({
  id: "op_001",
  op_type: "rotate",
  status: "pending",
  rotation_deg: 90,
  source: { hospital: "HRB", sigla: "altura", file: "a.pdf", page_range: null },
  dest: { hospital: "HRB", sigla: "altura" },
  ...over,
});

describe("pageRotation", () => {
  it("no ops → 0", () => {
    expect(pageRotation([], "HRB", "altura", "a.pdf", 1)).toBe(0);
  });

  it("whole-file op (page_range null/missing) rotates every page", () => {
    const ops = [op()];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 1)).toBe(90);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 99)).toBe(90);
  });

  it("missing page_range key (FileList ReorgMenu shape) = whole file", () => {
    const o = op();
    delete o.source.page_range;
    expect(pageRotation([o], "HRB", "altura", "a.pdf", 3)).toBe(90);
  });

  it("ranged op rotates only covered pages (1-based inclusive)", () => {
    const ops = [op({ source: { hospital: "HRB", sigla: "altura", file: "a.pdf", page_range: [3, 5] } })];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 2)).toBe(0);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 3)).toBe(90);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 5)).toBe(90);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 6)).toBe(0);
  });

  it("sums multiple pending ops mod 360", () => {
    const ops = [op(), op({ id: "op_002", rotation_deg: 270 })];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 1)).toBe(0); // 90+270
  });

  it("ignores applied ops, other files, other cells, other op types", () => {
    const ops = [
      op({ status: "applied" }),
      op({ id: "x", source: { hospital: "HRB", sigla: "altura", file: "b.pdf" } }),
      op({ id: "y", source: { hospital: "HLU", sigla: "altura", file: "a.pdf" } }),
      op({ id: "z", op_type: "extract_pages" }),
    ];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 1)).toBe(0);
  });

  it("missing status counts as pending (store ops may omit it)", () => {
    const o = op();
    delete o.status;
    expect(pageRotation([o], "HRB", "altura", "a.pdf", 1)).toBe(90);
  });
});

describe("rotationForPageFn", () => {
  it("binds ops+cell+file into a page->deg function", () => {
    const fn = rotationForPageFn([op()], "HRB", "altura", "a.pdf");
    expect(fn(1)).toBe(90);
  });
});
