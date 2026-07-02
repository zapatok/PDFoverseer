import { describe, it, expect } from "vitest";

import { computeWorkerCount, cellWorkerCount, fileSubtotal } from "./worker-count";

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

  it("F1: cuenta marca en archivo presente aunque no esté en per_file (presente != per_file)", () => {
    // Simula el escenario F1: b.pdf existe en disco pero pase-1 no lo registró
    // en per_file. La lista de archivos presentes incluye ambos → ambos deben
    // contar; el per_file-keyed filter hubiera excluido b.pdf.
    const marksF1 = {
      "a.pdf": [{ page: 1, count: 10 }],
      "b.pdf": [{ page: 1, count: 36 }],
    };
    // Llamada con lista de archivos en disco (presentes), no per_file keys.
    expect(computeWorkerCount(marksF1, ["a.pdf", "b.pdf"])).toBe(46);
  });
});

describe("cellWorkerCount (Incr J — reorg delta)", () => {
  const marks = {
    "a.pdf": [{ page: 1, count: 4 }],
  };

  it("sin delta: idéntico a computeWorkerCount", () => {
    const cell = { worker_marks: marks };
    expect(cellWorkerCount(cell, null)).toBe(4);
  });

  it("delta positivo suma al total de marcas", () => {
    const cell = { worker_marks: marks, reorg_worker_delta: 3 };
    expect(cellWorkerCount(cell, null)).toBe(7);
  });

  it("delta negativo resta al total de marcas", () => {
    const cell = { worker_marks: marks, reorg_worker_delta: -2 };
    expect(cellWorkerCount(cell, null)).toBe(2);
  });

  it("sin campo reorg_worker_delta (clave ausente) → sin cambio", () => {
    const cell = { worker_marks: marks };
    expect(cellWorkerCount(cell, null)).toBe(4);
  });

  it("celda null/undefined → 0 (sin error)", () => {
    expect(cellWorkerCount(null, null)).toBe(0);
    expect(cellWorkerCount(undefined, null)).toBe(0);
  });

  it("delta no afecta fileSubtotal (solo nivel de celda)", () => {
    // fileSubtotal reads worker_marks directly, not through cellWorkerCount
    const cell = { worker_marks: marks, reorg_worker_delta: 99 };
    expect(fileSubtotal(cell.worker_marks, "a.pdf")).toBe(4); // unchanged
  });

  it("clamps a negative effective worker total at 0 (F5)", () => {
    expect(cellWorkerCount({ worker_marks: {}, reorg_worker_delta: -3 }, null)).toBe(0);
  });
});
