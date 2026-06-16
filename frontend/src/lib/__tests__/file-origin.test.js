import { describe, it, expect } from "vitest";
import { fileCountDisplay } from "../file-origin";

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
  it("RN → shows effective count (default branch, no special case)", () => {
    expect(fileCountDisplay("RN", 4)).toEqual({ value: 4, placeholder: undefined });
  });
});
