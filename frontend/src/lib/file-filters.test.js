import { describe, expect, it } from "vitest";

import { countDiffersFromPages, FILTER_ORIGINS, matchesFilters } from "./file-filters";

describe("matchesFilters (FileList chip filters, E2)", () => {
  it("search-only, case-insensitive against file.name", () => {
    const file = { name: "Charla_Marzo.pdf", origin: "R1" };
    expect(matchesFilters(file, "charla", [])).toBe(true);
    expect(matchesFilters(file, "CHARLA", [])).toBe(true);
    expect(matchesFilters(file, "nomatch", [])).toBe(false);
  });

  it("origins-only: file must be in the active-origin set", () => {
    const file = { name: "a.pdf", origin: "OCR" };
    expect(matchesFilters(file, "", ["OCR"])).toBe(true);
    expect(matchesFilters(file, "", ["Manual"])).toBe(false);
    expect(matchesFilters(file, "", ["OCR", "Manual"])).toBe(true);
  });

  it("AND of search and origin — both must pass", () => {
    const file = { name: "Charla_Marzo.pdf", origin: "OCR" };
    expect(matchesFilters(file, "charla", ["OCR"])).toBe(true);
    expect(matchesFilters(file, "charla", ["Manual"])).toBe(false);
    expect(matchesFilters(file, "nomatch", ["OCR"])).toBe(false);
  });

  it("empty origin selection = no origin filter (today's behavior)", () => {
    const file = { name: "a.pdf", origin: "Error" };
    expect(matchesFilters(file, "", [])).toBe(true);
  });

  it("missing origin field defaults to R1", () => {
    const file = { name: "a.pdf" };
    expect(matchesFilters(file, "", ["R1"])).toBe(true);
    expect(matchesFilters(file, "", ["Manual"])).toBe(false);
  });

  it("empty search string passes everything (no filter)", () => {
    const file = { name: "anything.pdf", origin: "Pendiente" };
    expect(matchesFilters(file, "", [])).toBe(true);
  });

  it("FILTER_ORIGINS lists the 7 canonical origins", () => {
    expect(FILTER_ORIGINS).toEqual(["R1", "RN", "OCR", "Manual", "Pendiente", "Revisar", "Error"]);
  });
});

describe("countDiffersFromPages (FileList docs≠pages tint, E3)", () => {
  it("differs -> true, for a doc-counting count_type", () => {
    const file = { effective_count: 2, page_count: 5 };
    expect(countDiffersFromPages(file, "documents")).toBe(true);
    expect(countDiffersFromPages(file, "documents_workers")).toBe(true);
  });

  it("equal -> false", () => {
    const file = { effective_count: 3, page_count: 3 };
    expect(countDiffersFromPages(file, "documents")).toBe(false);
  });

  it("null count (Pendiente, not yet counted) -> false", () => {
    const file = { effective_count: null, page_count: 5 };
    expect(countDiffersFromPages(file, "documents")).toBe(false);
  });

  it("null page_count -> false", () => {
    const file = { effective_count: 2, page_count: null };
    expect(countDiffersFromPages(file, "documents")).toBe(false);
  });

  it("checks count_type -> always false (excluded by isCappedCountType)", () => {
    const file = { effective_count: 2, page_count: 5 };
    expect(countDiffersFromPages(file, "checks")).toBe(false);
  });

  it("undefined count_type -> false (not a capped type)", () => {
    const file = { effective_count: 2, page_count: 5 };
    expect(countDiffersFromPages(file, undefined)).toBe(false);
  });
});
