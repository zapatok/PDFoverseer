import { describe, expect, it } from "vitest";

import { DEFAULT_ROTATION_DEG, ROTATION_OPTIONS } from "./rotation-options";

describe("rotation-options", () => {
  // La invariante que se violó (2026-07-10): el default del estado del select
  // no existía entre las opciones → ops rotate con rotation_deg 0 (no-op).
  it("el default es una de las opciones visibles del select", () => {
    expect(ROTATION_OPTIONS.map((o) => o.value)).toContain(DEFAULT_ROTATION_DEG);
  });

  it("ninguna opción es 0 (rotar 0° es un no-op sin sentido)", () => {
    for (const o of ROTATION_OPTIONS) {
      expect([90, 180, 270]).toContain(o.value);
    }
  });

  it("cada opción indica dirección o es simétrica (180°)", () => {
    for (const o of ROTATION_OPTIONS) {
      if (o.value !== 180) {
        expect(o.label).toMatch(/derecha|izquierda/);
      }
    }
  });
});
