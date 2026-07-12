import { describe, it, expect } from "vitest";
import { applyRangeKey, isValidRange, normalizeRange } from "./reorg-range";

describe("reorg range", () => {
  it("accepts in-bounds start<=end", () => {
    expect(isValidRange(1, 3, 10)).toBe(true);
    expect(isValidRange(5, 5, 10)).toBe(true);
  });
  it("rejects out-of-bounds or inverted", () => {
    expect(isValidRange(0, 3, 10)).toBe(false);
    expect(isValidRange(3, 11, 10)).toBe(false);
    expect(isValidRange(5, 3, 10)).toBe(false);
    expect(isValidRange(null, 3, 10)).toBe(false);
    expect(isValidRange(3, null, 10)).toBe(false);
  });
  it("normalizes [start,end] sorted", () => {
    expect(normalizeRange(5, 3)).toEqual([3, 5]);
    expect(normalizeRange(2, 4)).toEqual([2, 4]);
  });
});

// §4 (Track D, Chunk D3, Task 9) — pure reducer for the reorg viewer's
// keyboard range marking ([ ] Escape). Shared by the keyboard handler AND
// the mouse "Marcar inicio/fin" buttons (WorkerCountViewer.jsx) so both input
// methods stay in sync.
describe("applyRangeKey", () => {
  it("[ marks start at the current page (no end marked yet)", () => {
    expect(applyRangeKey("[", { start: null, end: null }, 5)).toEqual({ start: 5, end: null });
  });
  it("] marks end at the current page (no start marked yet)", () => {
    expect(applyRangeKey("]", { start: null, end: null }, 7)).toEqual({ start: null, end: 7 });
  });
  it("] after an earlier start keeps order", () => {
    expect(applyRangeKey("]", { start: 2, end: null }, 7)).toEqual({ start: 2, end: 7 });
  });
  it("[ always writes the start slot, even past the already-marked end (no swap)", () => {
    expect(applyRangeKey("[", { start: null, end: 3 }, 8)).toEqual({ start: 8, end: 3 });
  });
  it("] always writes the end slot, even before the already-marked start (no swap) — but normalizeRange/isValidRange (one layer up) still treat the out-of-order pair as a valid range", () => {
    const next = applyRangeKey("]", { start: 8, end: null }, 3);
    expect(next).toEqual({ start: 8, end: 3 });
    expect(normalizeRange(next.start, next.end)).toEqual([3, 8]);
    expect(isValidRange(...normalizeRange(next.start, next.end), 10)).toBe(true);
  });
  it("marking start==end is a valid single-page range once normalized", () => {
    const next = applyRangeKey("[", { start: null, end: 5 }, 5);
    expect(next).toEqual({ start: 5, end: 5 });
    expect(isValidRange(...normalizeRange(next.start, next.end), 10)).toBe(true);
  });
  it("Escape clears both bounds regardless of current page", () => {
    expect(applyRangeKey("Escape", { start: 2, end: 7 }, 4)).toEqual({ start: null, end: null });
    expect(applyRangeKey("Escape", { start: null, end: null }, 1)).toEqual({ start: null, end: null });
  });
  it("unknown keys are a no-op (returns the same range)", () => {
    const range = { start: 2, end: 7 };
    expect(applyRangeKey("x", range, 4)).toBe(range);
  });
});
