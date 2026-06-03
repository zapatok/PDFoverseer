import { describe, expect, it } from "vitest";

import { dotVariantFor, hasOverride, isCellReady } from "./cell-status";

describe("isCellReady", () => {
  it("is ready when scanner confidence is high", () => {
    expect(isCellReady({ confidence: "high" })).toBe(true);
  });

  it("is ready when manually confirmed even if confidence is low", () => {
    expect(isCellReady({ confidence: "low", confirmed: true })).toBe(true);
  });

  it("is ready when a user override is present (including 0)", () => {
    expect(isCellReady({ confidence: "low", user_override: 5 })).toBe(true);
    expect(isCellReady({ confidence: "low", user_override: 0 })).toBe(true);
  });

  it("is pendiente when low and none of the above", () => {
    expect(isCellReady({ confidence: "low" })).toBe(false);
    expect(
      isCellReady({ confidence: "low", confirmed: false, user_override: null }),
    ).toBe(false);
  });
});

describe("hasOverride", () => {
  it("treats 0 as an override but null/undefined as none", () => {
    expect(hasOverride({ user_override: 0 })).toBe(true);
    expect(hasOverride({ user_override: null })).toBe(false);
    expect(hasOverride({})).toBe(false);
  });
});

describe("dotVariantFor", () => {
  it("scanning takes precedence over everything", () => {
    expect(dotVariantFor({ confidence: "high" }, { isScanning: true })).toBe(
      "state-scanning",
    );
  });

  it("error takes precedence over readiness", () => {
    expect(dotVariantFor({ confidence: "high", errors: ["boom"] })).toBe(
      "state-error",
    );
  });

  it("ready -> green, pendiente -> amber", () => {
    expect(dotVariantFor({ confidence: "high" })).toBe("confidence-high");
    expect(dotVariantFor({ confidence: "low" })).toBe("confidence-low");
    expect(dotVariantFor({ confidence: "low", confirmed: true })).toBe(
      "confidence-high",
    );
  });

  it("a cell with no data yet stays neutral", () => {
    expect(dotVariantFor(undefined)).toBe("neutral");
    expect(dotVariantFor(null)).toBe("neutral");
  });
});
