import { describe, it, expect } from "vitest";
import { isValidRange, normalizeRange } from "./reorg-range";

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
  });
  it("normalizes [start,end] sorted", () => {
    expect(normalizeRange(5, 3)).toEqual([3, 5]);
    expect(normalizeRange(2, 4)).toEqual([2, 4]);
  });
});
