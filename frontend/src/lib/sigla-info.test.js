import { describe, expect, it } from "vitest";

import { SIGLAS } from "./sigla-labels";
import { SIGLA_DESCRIPTION, SIGLA_PAGE_RANGE, formatPageRange, SIGLA_COUNT_TYPE, countTypeFor } from "./sigla-info";

describe("sigla-info", () => {
  it("covers all 20 siglas", () => {
    for (const s of SIGLAS) {
      expect(typeof SIGLA_DESCRIPTION[s]).toBe("string");
      expect(SIGLA_DESCRIPTION[s].length).toBeGreaterThan(0);
      expect(SIGLA_PAGE_RANGE[s]).toBeTruthy();
    }
  });

  it("formats a range, a single value, and the 1-page case", () => {
    expect(formatPageRange({ p25: 4, p75: 6 })).toBe(
      "Suele tener 4–6 páginas por documento.",
    );
    expect(formatPageRange({ p25: 1, p75: 1 })).toBe("Normalmente 1 página.");
    expect(formatPageRange({ p25: 2, p75: 2 })).toBe("Suele tener 2 páginas.");
  });
});

describe("SIGLA_COUNT_TYPE", () => {
  const VALID_TYPES = new Set(["documents", "documents_workers", "checks"]);

  it("covers all 20 siglas with a valid count_type", () => {
    for (const s of SIGLAS) {
      expect(SIGLA_COUNT_TYPE[s], `${s} must have a count_type`).toBeDefined();
      expect(VALID_TYPES.has(SIGLA_COUNT_TYPE[s]), `${s} count_type must be valid`).toBe(true);
    }
  });

  it("maquinaria is checks", () => {
    expect(SIGLA_COUNT_TYPE["maquinaria"]).toBe("checks");
  });

  it("charla, chintegral, dif_pts are documents_workers", () => {
    expect(SIGLA_COUNT_TYPE["charla"]).toBe("documents_workers");
    expect(SIGLA_COUNT_TYPE["chintegral"]).toBe("documents_workers");
    expect(SIGLA_COUNT_TYPE["dif_pts"]).toBe("documents_workers");
  });

  it("countTypeFor returns the correct type for known siglas", () => {
    expect(countTypeFor("maquinaria")).toBe("checks");
    expect(countTypeFor("charla")).toBe("documents_workers");
    expect(countTypeFor("reunion")).toBe("documents");
  });

  it("countTypeFor defaults to documents for unknown siglas", () => {
    expect(countTypeFor("unknown_sigla")).toBe("documents");
  });
});
