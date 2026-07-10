import { describe, expect, it } from "vitest";

import { FILTER_ORIGINS, matchesFilters } from "./file-filters";

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
