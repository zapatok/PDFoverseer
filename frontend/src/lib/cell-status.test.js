import { describe, expect, it } from "vitest";

import {
  allFilesReliable,
  anyUnreliableOcrFile,
  dotVariantFor,
  hasOverride,
  isCellReady,
} from "./cell-status";

describe("isCellReady (honest provenance)", () => {
  it("all-R1 single-page cell (high, filename_glob) -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "filename_glob" } }),
    ).toBe(true);
  });

  it("fixed-page sigla (high, page_count_pure) -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "page_count_pure" } }),
    ).toBe(true);
  });

  it("multipage no-OCR cell (low) -> NOT ready", () => {
    expect(
      isCellReady({ confidence: "low", per_file_method: { "a.pdf": "filename_glob" } }),
    ).toBe(false);
  });

  it("clean OCR cell (high) -> NOT ready (the honest change)", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" } }),
    ).toBe(false);
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "header_band_anchors" } }),
    ).toBe(false);
  });

  it("OCR cell + confirmed -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" }, confirmed: true }),
    ).toBe(true);
  });

  it("OCR cell + cell-level override -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" }, user_override: 5 }),
    ).toBe(true);
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" }, user_override: 0 }),
    ).toBe(true);
  });

  it("mix R1 + one OCR file -> NOT ready", () => {
    expect(
      isCellReady({
        confidence: "high",
        per_file_method: { "a.pdf": "filename_glob", "b.pdf": "v4" },
      }),
    ).toBe(false);
  });

  it("mix R1 + OCR file overridden per-file -> ready", () => {
    expect(
      isCellReady({
        confidence: "high",
        per_file_method: { "a.pdf": "filename_glob", "b.pdf": "v4" },
        per_file_overrides: { "b.pdf": 3 },
      }),
    ).toBe(true);
    // a 0 per-file override still counts as Manual (reliable)
    expect(
      isCellReady({
        confidence: "high",
        per_file_method: { "b.pdf": "v4" },
        per_file_overrides: { "b.pdf": 0 },
      }),
    ).toBe(true);
  });

  it("empty per_file_method with high confidence -> ready (no OCR evidence)", () => {
    expect(isCellReady({ confidence: "high" })).toBe(true);
    expect(isCellReady({ confidence: "high", per_file_method: {} })).toBe(true);
  });

  it("manually confirmed even if confidence low -> ready", () => {
    expect(isCellReady({ confidence: "low", confirmed: true })).toBe(true);
  });
});

describe("anyUnreliableOcrFile", () => {
  it("true only for an OCR method without a per-file override", () => {
    expect(anyUnreliableOcrFile({ per_file_method: { "a.pdf": "v4" } })).toBe(true);
    expect(
      anyUnreliableOcrFile({ per_file_method: { "a.pdf": "v4" }, per_file_overrides: { "a.pdf": 2 } }),
    ).toBe(false);
    expect(anyUnreliableOcrFile({ per_file_method: { "a.pdf": "filename_glob" } })).toBe(false);
    expect(anyUnreliableOcrFile({ per_file_method: { "a.pdf": "page_count_pure" } })).toBe(false);
    expect(anyUnreliableOcrFile({})).toBe(false);
  });
});

describe("allFilesReliable", () => {
  it("requires high confidence AND no unreliable OCR file", () => {
    expect(allFilesReliable({ confidence: "high", per_file_method: { "a.pdf": "filename_glob" } })).toBe(true);
    expect(allFilesReliable({ confidence: "low", per_file_method: { "a.pdf": "filename_glob" } })).toBe(false);
    expect(allFilesReliable({ confidence: "high", per_file_method: { "a.pdf": "v4" } })).toBe(false);
  });
});

describe("hasOverride", () => {
  it("treats 0 as an override but null/undefined as none", () => {
    expect(hasOverride({ user_override: 0 })).toBe(true);
    expect(hasOverride({ user_override: null })).toBe(false);
    expect(hasOverride({})).toBe(false);
  });
});

describe("isCellReady (Incr 2 — all_reliable signal)", () => {
  it("all_reliable true -> ready", () => {
    expect(isCellReady({ all_reliable: true })).toBe(true);
  });
  it("all_reliable false -> not ready (even if confidence high)", () => {
    expect(isCellReady({ all_reliable: false, confidence: "high" })).toBe(false);
  });
  it("all_reliable absent -> falls back to 1B legacy rule", () => {
    // legacy: confidence high + no unreliable OCR file
    expect(isCellReady({ confidence: "high", per_file_method: { "a.pdf": "filename_glob" } })).toBe(true);
    expect(isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" } })).toBe(false);
  });
  it("confirmed / cell override still win regardless of all_reliable", () => {
    expect(isCellReady({ all_reliable: false, confirmed: true })).toBe(true);
    expect(isCellReady({ all_reliable: false, user_override: 5 })).toBe(true);
  });
});

describe("isCellReady (checks branch — Incr 3A)", () => {
  it("checks cell ready only when worker_status is terminado", () => {
    expect(isCellReady({ worker_status: "terminado" }, "checks")).toBe(true);
    expect(isCellReady({ worker_status: "en_progreso" }, "checks")).toBe(false);
    expect(isCellReady({}, "checks")).toBe(false);
  });
  it("checks: confirmed/override still win", () => {
    expect(isCellReady({ worker_status: "en_progreso", confirmed: true }, "checks")).toBe(true);
    expect(isCellReady({ worker_status: "en_progreso", user_override: 3 }, "checks")).toBe(true);
  });
  it("checks dot shows green only on terminado", () => {
    expect(dotVariantFor({ worker_status: "terminado" }, { countType: "checks" })).toBe("confidence-high");
    expect(dotVariantFor({ worker_status: "en_progreso" }, { countType: "checks" })).toBe("confidence-low");
  });
  it("documents countType unaffected — backward compat", () => {
    expect(isCellReady({ confidence: "high", per_file_method: { "a.pdf": "filename_glob" } }, "documents")).toBe(true);
    expect(isCellReady({ all_reliable: true }, "documents")).toBe(true);
  });
});

describe("dotVariantFor", () => {
  it("scanning takes precedence over everything", () => {
    expect(dotVariantFor({ confidence: "high" }, { isScanning: true })).toBe("state-scanning");
  });
  it("error takes precedence over readiness", () => {
    expect(dotVariantFor({ confidence: "high", errors: ["boom"] })).toBe("state-error");
  });
  it("ready -> green, pendiente -> amber", () => {
    expect(dotVariantFor({ confidence: "high" })).toBe("confidence-high");
    expect(dotVariantFor({ confidence: "low" })).toBe("confidence-low");
    expect(dotVariantFor({ confidence: "high", per_file_method: { "a.pdf": "v4" } })).toBe("confidence-low");
    expect(dotVariantFor({ confidence: "low", confirmed: true })).toBe("confidence-high");
  });
  it("a cell with no data yet stays neutral", () => {
    expect(dotVariantFor(undefined)).toBe("neutral");
    expect(dotVariantFor(null)).toBe("neutral");
  });
});
