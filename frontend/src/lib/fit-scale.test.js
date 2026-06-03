import { describe, it, expect } from "vitest";

import { computeFitScale } from "./fit-scale";

describe("computeFitScale", () => {
  it("limita por ancho cuando la página es relativamente más ancha", () => {
    // página 1000x500, panel 500x500 → min(0.5, 1.0)
    expect(computeFitScale({ width: 1000, height: 500 }, { width: 500, height: 500 })).toBe(0.5);
  });

  it("limita por alto cuando la página es relativamente más alta", () => {
    // página 500x1000, panel 500x500 → min(1.0, 0.5)
    expect(computeFitScale({ width: 500, height: 1000 }, { width: 500, height: 500 })).toBe(0.5);
  });

  it("amplía si el panel es mayor que la página (contain, no clamp a 1)", () => {
    expect(computeFitScale({ width: 250, height: 250 }, { width: 500, height: 500 })).toBe(2);
  });

  it("devuelve 1 si alguna dimensión es 0 (guard de división por cero)", () => {
    expect(computeFitScale({ width: 0, height: 500 }, { width: 500, height: 500 })).toBe(1);
    expect(computeFitScale({ width: 500, height: 500 }, { width: 500, height: 0 })).toBe(1);
    expect(computeFitScale(null, null)).toBe(1);
  });
});
