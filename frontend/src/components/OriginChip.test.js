import { describe, expect, it } from "vitest";

import { ORIGIN_VARIANT, originVariant } from "./OriginChip";

describe("originVariant", () => {
  it("maps each known origin to its Badge tone", () => {
    expect(originVariant("OCR")).toBe("iris");
    expect(originVariant("R1")).toBe("jade");
    expect(originVariant("manual")).toBe("amber");
  });

  it("maps page-count cells (Estructura) to a distinct blue tone", () => {
    expect(originVariant("Estructura")).toBe("blue");
    // Distinct from OCR so a structural count never reads as OCR.
    expect(ORIGIN_VARIANT.Estructura).not.toBe(ORIGIN_VARIANT.OCR);
  });

  it("falls back to neutral for an unknown origin", () => {
    expect(originVariant("???")).toBe("neutral");
    expect(originVariant(undefined)).toBe("neutral");
  });
});
