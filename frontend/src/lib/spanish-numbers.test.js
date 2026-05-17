import { describe, expect, it } from "vitest";

import cases from "./spanish-numbers.cases.json";
import { parseSpanishNumber } from "./spanish-numbers";

describe("parseSpanishNumber", () => {
  it.each(cases)("«$input» → $expected", ({ input, expected }) => {
    expect(parseSpanishNumber(input)).toBe(expected);
  });

  it("la conjunción «y» suelta no es un número", () => {
    expect(parseSpanishNumber("y")).toBe(null);
  });

  it("una suma que supera 999 se descarta", () => {
    expect(parseSpanishNumber("novecientos noventa y nueve y uno")).toBe(null);
  });
});
