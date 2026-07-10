import { describe, it, expect } from "vitest";
import { parseGoToPage } from "./go-to-page";

describe("parseGoToPage", () => {
  it("parses an in-range integer as-is", () => {
    expect(parseGoToPage("7", 10)).toBe(7);
  });
  it("clamps below 1 up to 1", () => {
    expect(parseGoToPage("0", 10)).toBe(1);
    expect(parseGoToPage("-5", 10)).toBe(1);
  });
  it("clamps above pageCount down to pageCount", () => {
    expect(parseGoToPage("999", 10)).toBe(10);
  });
  it("returns null for non-numeric input", () => {
    expect(parseGoToPage("abc", 10)).toBeNull();
  });
  it("returns null for an empty string (Number('')===0 trap)", () => {
    expect(parseGoToPage("", 10)).toBeNull();
  });
  it("returns null when pageCount is 0", () => {
    expect(parseGoToPage("1", 0)).toBeNull();
  });
});
