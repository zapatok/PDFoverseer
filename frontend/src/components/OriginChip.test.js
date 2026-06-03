import { describe, expect, it } from "vitest";

import { ORIGIN_VARIANT, originVariant } from "./OriginChip";

describe("originVariant", () => {
  it("maps the five canonical origins to tones", () => {
    expect(originVariant("R1")).toBe("jade");
    expect(originVariant("OCR")).toBe("iris");
    expect(originVariant("Manual")).toBe("blue");
    expect(originVariant("Pendiente")).toBe("amber");
    expect(originVariant("Error")).toBe("state-error");
  });

  it("keeps OCR and R1 visually distinct", () => {
    expect(ORIGIN_VARIANT.OCR).not.toBe(ORIGIN_VARIANT.R1);
  });

  it("falls back to neutral for an unknown origin", () => {
    expect(originVariant("???")).toBe("neutral");
    expect(originVariant(undefined)).toBe("neutral");
  });
});
