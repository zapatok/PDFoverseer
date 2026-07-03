import { describe, expect, it } from "vitest";

import {
  allFilesReliable,
  anyUnreliableOcrFile,
  dotVariantFor,
  hasOverride,
  hospitalWorkerStatus,
  isCellReady,
  perFileCountEditable,
  showsWorkerCounter,
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

describe("showsWorkerCounter", () => {
  it("shows for documents_workers (charla/chintegral/dif_pts)", () => {
    expect(showsWorkerCounter("documents_workers")).toBe(true);
  });
  it("shows for checks (maquinaria)", () => {
    expect(showsWorkerCounter("checks")).toBe(true);
  });
  it("hides for plain documents", () => {
    expect(showsWorkerCounter("documents")).toBe(false);
  });
  it("hides for unknown/undefined count_type", () => {
    expect(showsWorkerCounter(undefined)).toBe(false);
  });
});

describe("isCellReady — por_resolver note gate", () => {
  it("forces not-ready even when confirmed", () => {
    expect(isCellReady({ confirmed: true, note_status: "por_resolver" })).toBe(false);
  });
  it("forces not-ready even with an override", () => {
    expect(isCellReady({ user_override: 5, note_status: "por_resolver" })).toBe(false);
  });
  it("forces not-ready even when checks terminado", () => {
    expect(
      isCellReady({ worker_status: "terminado", note_status: "por_resolver" }, "checks"),
    ).toBe(false);
  });
  it("resuelto does not block (confirmed stays ready)", () => {
    expect(isCellReady({ confirmed: true, note_status: "resuelto" })).toBe(true);
  });
  it("no note behaves as before", () => {
    expect(isCellReady({ confirmed: true })).toBe(true);
  });
  it("dotVariantFor → confidence-low when por_resolver", () => {
    expect(dotVariantFor({ confirmed: true, note_status: "por_resolver" })).toBe("confidence-low");
  });
});

describe("hospitalWorkerStatus", () => {
  const filesCell = (extra) => ({ per_file: { "a.pdf": 1 }, ...extra });

  it("null when no worker cells have files", () => {
    expect(hospitalWorkerStatus({ reunion: filesCell() })).toBe(null); // reunion = documents
    expect(hospitalWorkerStatus({ charla: { per_file: {} } })).toBe(null);
    expect(hospitalWorkerStatus({})).toBe(null);
    expect(hospitalWorkerStatus(null)).toBe(null);
  });

  it("listo when all relevant worker cells terminado", () => {
    const cells = {
      charla: filesCell({ worker_status: "terminado" }),
      maquinaria: filesCell({ worker_status: "terminado" }),
    };
    expect(hospitalWorkerStatus(cells)).toBe("listo");
  });

  it("pendiente when none started", () => {
    const cells = { charla: filesCell(), dif_pts: filesCell() };
    expect(hospitalWorkerStatus(cells)).toBe("pendiente");
  });

  it("en_proceso when some started but not all done", () => {
    const cells = {
      charla: filesCell({ worker_status: "terminado" }),
      chintegral: filesCell({ worker_marks: { "a.pdf": [{ page: 1, count: 2 }] } }),
    };
    expect(hospitalWorkerStatus(cells)).toBe("en_proceso");
  });

  it("worker cell without files is ignored", () => {
    const cells = {
      charla: filesCell({ worker_status: "terminado" }),
      dif_pts: { per_file: {}, worker_status: "en_progreso" }, // no files → excluded
    };
    expect(hospitalWorkerStatus(cells)).toBe("listo");
  });

  it("counts a worker cell relevant via the doc-count fallback (no per_file)", () => {
    // cellHasFiles fallback: per_file absent but documents > 0 → still relevant.
    expect(
      hospitalWorkerStatus({ charla: { filename_count: 3, worker_status: "terminado" } }),
    ).toBe("listo");
    // Relevant via fallback but not started → pendiente.
    expect(hospitalWorkerStatus({ charla: { ocr_count: 5 } })).toBe("pendiente");
  });
});

describe("OCR_METHODS — pagination chip (Task 12)", () => {
  it("pagination method is treated as OCR (unreliable without override)", () => {
    expect(anyUnreliableOcrFile({ per_file_method: { "a.pdf": "pagination" } })).toBe(true);
  });

  it("pagination file with per-file override is reliable", () => {
    expect(
      anyUnreliableOcrFile({
        per_file_method: { "a.pdf": "pagination" },
        per_file_overrides: { "a.pdf": 3 },
      }),
    ).toBe(false);
  });

  it("cell with pagination method is not allFilesReliable", () => {
    expect(
      allFilesReliable({ confidence: "high", per_file_method: { "a.pdf": "pagination" } }),
    ).toBe(false);
  });

  it("dotVariantFor → amber for pagination without override (same as v4)", () => {
    expect(
      dotVariantFor({ confidence: "high", per_file_method: { "a.pdf": "pagination" } }),
    ).toBe("confidence-low");
  });
});

describe("perFileCountEditable (U3)", () => {
  it("checks (maquinaria) is read-only — the tally comes from marks, not per-file", () => {
    expect(perFileCountEditable("checks")).toBe(false);
  });
  it("documents stays editable", () => {
    expect(perFileCountEditable("documents")).toBe(true);
  });
  it("documents_workers stays editable — its cell number IS the document count", () => {
    expect(perFileCountEditable("documents_workers")).toBe(true);
  });
  it("unknown/undefined count_type defaults editable", () => {
    expect(perFileCountEditable(undefined)).toBe(true);
  });
});
