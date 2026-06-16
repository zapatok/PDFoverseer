import { describe, expect, it } from "vitest";

import { parseOverrideInput } from "./override-input";

describe("parseOverrideInput", () => {
  it("empty/null clears the override (value null, valid)", () => {
    expect(parseOverrideInput("")).toEqual({ value: null, valid: true });
    expect(parseOverrideInput(null)).toEqual({ value: null, valid: true });
    expect(parseOverrideInput(undefined)).toEqual({ value: null, valid: true });
  });

  it("0 is a valid override", () => {
    expect(parseOverrideInput("0")).toEqual({ value: 0, valid: true });
  });

  it("positive integers are valid", () => {
    expect(parseOverrideInput("12")).toEqual({ value: 12, valid: true });
  });

  it("negatives are invalid", () => {
    expect(parseOverrideInput("-5")).toEqual({ value: null, valid: false });
  });

  it("non-numeric is invalid", () => {
    expect(parseOverrideInput("abc")).toEqual({ value: null, valid: false });
  });

  it("alphanumeric prefix is invalid (no silent parseInt truncation)", () => {
    expect(parseOverrideInput("5abc")).toEqual({ value: null, valid: false });
  });

  it("non-integers are invalid (a document count is whole)", () => {
    expect(parseOverrideInput("5.5")).toEqual({ value: null, valid: false });
  });
});
