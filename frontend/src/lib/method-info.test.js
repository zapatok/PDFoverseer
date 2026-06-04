import { describe, expect, it } from "vitest";

import { METHOD_INFO, composeMethodInfo } from "./method-info";
import { METHOD_LABEL } from "./method-labels";

describe("METHOD_INFO", () => {
  it("has an explanation for every labelled method", () => {
    for (const token of Object.keys(METHOD_LABEL)) {
      expect(typeof METHOD_INFO[token]).toBe("string");
      expect(METHOD_INFO[token].length).toBeGreaterThan(0);
    }
  });
});

describe("composeMethodInfo", () => {
  it("composes anchor-based OCR info from scan-info", () => {
    const t = composeMethodInfo("header_band_anchors", {
      kind: "anchors",
      looks_for: ["antecedentes generales", "tipo de inducción"],
    });
    expect(t).toMatch(/Busca:/);
    expect(t).toMatch(/antecedentes generales/);
    expect(t).toMatch(/tipo de inducción/);
  });

  it("describes pagination siglas", () => {
    expect(composeMethodInfo("v4", { kind: "pagination" })).toMatch(/Página N de M/);
  });

  it("falls back per method without scan-info", () => {
    expect(composeMethodInfo("filename_glob", null)).toMatch(/archivo/i);
    expect(composeMethodInfo("manual", null)).toMatch(/a mano/i);
  });
});
