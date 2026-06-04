import { describe, expect, it } from "vitest";

import { SIGLAS } from "./sigla-labels";
import { SIGLA_DESCRIPTION, SIGLA_PAGE_RANGE, formatPageRange } from "./sigla-info";

describe("sigla-info", () => {
  it("covers all 18 siglas", () => {
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
