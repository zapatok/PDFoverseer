import { describe, it, expect } from "vitest";
import { evaluate } from "./calc";

describe("evaluate (viewer calculator, I8)", () => {
  it("respects operator precedence", () => {
    expect(evaluate("2+3*4")).toBe(14);
  });
  it("respects parentheses", () => {
    expect(evaluate("(2+3)*4")).toBe(20);
  });
  it("divides", () => {
    expect(evaluate("10/4")).toBe(2.5);
  });
  it("handles unary minus", () => {
    expect(evaluate("-3+5")).toBe(2);
  });
  it("handles decimals", () => {
    expect(evaluate("1.5*2")).toBe(3);
  });
  it("rejects a malformed expression (double operator)", () => {
    expect(evaluate("2++2")).toBeNull();
  });
  it("rejects an unclosed parenthesis", () => {
    expect(evaluate("(2")).toBeNull();
  });
  it("rejects non-numeric input", () => {
    expect(evaluate("abc")).toBeNull();
  });
  it("rejects the empty string", () => {
    expect(evaluate("")).toBeNull();
  });
  it("rejects division by zero (Infinity is not a valid result)", () => {
    expect(evaluate("8/0")).toBeNull();
  });
});
