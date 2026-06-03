import { describe, it, expect } from "vitest";

import { computeWorkerCount } from "./worker-count";

describe("computeWorkerCount", () => {
  const marks = {
    "a.pdf": [{ page: 1, count: 3 }, { page: 2, count: 2 }],
    "b.pdf": [{ page: 1, count: 5 }],
  };

  it("cuenta TODAS las marcas cuando fileNames es un array vacío (celda sin escanear)", () => {
    // Reproduce el bug: el DetailPanel pasa Object.keys({}) === [] (truthy en JS).
    expect(computeWorkerCount(marks, [])).toBe(10);
  });

  it("cuenta todas las marcas cuando fileNames es null/undefined", () => {
    expect(computeWorkerCount(marks, null)).toBe(10);
    expect(computeWorkerCount(marks, undefined)).toBe(10);
  });

  it("filtra las marcas huérfanas cuando hay una lista de archivos presente", () => {
    expect(computeWorkerCount(marks, ["a.pdf"])).toBe(5); // 3 + 2, sin b.pdf
  });

  it("regresión: Object.keys de un per_file vacío sigue sumando", () => {
    expect(computeWorkerCount(marks, Object.keys({}))).toBe(10);
  });

  it("devuelve 0 sin marcas", () => {
    expect(computeWorkerCount({}, [])).toBe(0);
    expect(computeWorkerCount(null, null)).toBe(0);
  });
});
