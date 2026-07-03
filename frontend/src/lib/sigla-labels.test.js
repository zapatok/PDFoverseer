import { describe, expect, it } from "vitest";

import { SIGLA_LABELS, SIGLAS, siglaDisplay } from "./sigla-labels";

describe("SIGLA_LABELS", () => {
  it("covers all 20 siglas with a non-empty label", () => {
    expect(SIGLAS.length).toBe(20);
    for (const s of SIGLAS) {
      expect(typeof SIGLA_LABELS[s], `${s} must have a label`).toBe("string");
      expect(SIGLA_LABELS[s].length, `${s} label must be non-empty`).toBeGreaterThan(0);
    }
  });
});

describe("siglaDisplay", () => {
  it("overrides chps to the real acronym cphs", () => {
    expect(siglaDisplay("chps")).toBe("cphs");
  });

  it("passes through a sigla with no override unchanged", () => {
    expect(siglaDisplay("art")).toBe("art");
  });
});
