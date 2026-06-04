import { describe, it, expect } from "vitest";
import { fileCountDisplay, ORIGIN_RANK, compareByOrigin } from "../file-origin";

describe("fileCountDisplay", () => {
  it("Pendiente → null value + em-dash placeholder (still editable)", () => {
    expect(fileCountDisplay("Pendiente", 1)).toEqual({ value: null, placeholder: "—" });
  });
  it("Revisar → shows the real 0", () => {
    expect(fileCountDisplay("Revisar", 0)).toEqual({ value: 0, placeholder: undefined });
  });
  it("OCR/Manual/R1 → effective count", () => {
    expect(fileCountDisplay("OCR", 17)).toEqual({ value: 17, placeholder: undefined });
    expect(fileCountDisplay("R1", 1)).toEqual({ value: 1, placeholder: undefined });
  });
  it("missing count → defaults to 1 (non-Pendiente)", () => {
    expect(fileCountDisplay("R1", undefined)).toEqual({ value: 1, placeholder: undefined });
  });
});

describe("ORIGIN_RANK", () => {
  it("orders the six known origins by urgency", () => {
    expect(ORIGIN_RANK).toEqual({
      Error: 0,
      Pendiente: 1,
      Revisar: 2,
      Manual: 3,
      OCR: 4,
      R1: 5,
    });
  });
});

describe("compareByOrigin", () => {
  it("orders Error → Pendiente → Revisar → Manual → OCR → R1", () => {
    const rows = [
      { name: "d.pdf", origin: "R1" },
      { name: "a.pdf", origin: "OCR" },
      { name: "b.pdf", origin: "Error" },
      { name: "c.pdf", origin: "Manual" },
      { name: "e.pdf", origin: "Pendiente" },
      { name: "f.pdf", origin: "Revisar" },
    ];
    const sorted = [...rows].sort(compareByOrigin).map((r) => r.origin);
    expect(sorted).toEqual(["Error", "Pendiente", "Revisar", "Manual", "OCR", "R1"]);
  });
  it("ties broken by filename within the same origin", () => {
    const rows = [
      { name: "2026-04-30_x.pdf", origin: "Pendiente" },
      { name: "2026-04-02_x.pdf", origin: "Pendiente" },
    ];
    const sorted = [...rows].sort(compareByOrigin).map((r) => r.name);
    expect(sorted).toEqual(["2026-04-02_x.pdf", "2026-04-30_x.pdf"]);
  });
  it("unknown origin sorts last", () => {
    const rows = [{ name: "a", origin: "???" }, { name: "b", origin: "R1" }];
    const sorted = [...rows].sort(compareByOrigin).map((r) => r.origin);
    expect(sorted).toEqual(["R1", "???"]);
  });
});
