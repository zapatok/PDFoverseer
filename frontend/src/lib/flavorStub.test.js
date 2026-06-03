import { describe, expect, it } from "vitest";
import { buildFlavorStub } from "./flavorStub";

const NM = {
  pdf_name: "ejemplo.pdf",
  page_index: 3,
  flavor_name: "f_lch_05",
  matched_anchors: ["LISTA DE CHEQUEO", "Empresa"],
  missing_anchors: ["Código"],
};

describe("buildFlavorStub", () => {
  it("incluye el nombre del PDF y la página (1-based) en el comentario de encabezado", () => {
    const stub = buildFlavorStub(NM);
    expect(stub).toContain("ejemplo.pdf p.4");
  });

  it("incluye el flavor de referencia", () => {
    const stub = buildFlavorStub(NM);
    expect(stub).toContain("f_lch_05");
  });

  it("escribe las anclas coincidentes sin comentar", () => {
    const stub = buildFlavorStub(NM);
    expect(stub).toContain('"LISTA DE CHEQUEO",');
    expect(stub).toContain('"Empresa",');
  });

  it("escribe las anclas faltantes comentadas con el PDF de origen", () => {
    const stub = buildFlavorStub(NM);
    expect(stub).toContain('# "Código",');
    expect(stub).toContain("faltó en ejemplo.pdf");
  });

  it("aplica un piso de 3 a min_match cuando hay pocas anclas coincidentes", () => {
    // NM tiene 2 anclas coincidentes → max(3, 2) = 3
    const stub = buildFlavorStub(NM);
    expect(stub).toContain("min_match=3,");
  });

  it("usa el número de anclas coincidentes cuando supera el piso de 3", () => {
    const nm = { ...NM, matched_anchors: ["A", "B", "C", "D"] };
    const stub = buildFlavorStub(nm);
    expect(stub).toContain("min_match=4,");
  });

  it("sin anclas faltantes no aparecen líneas de anclas comentadas", () => {
    const nm = { ...NM, missing_anchors: [] };
    const stub = buildFlavorStub(nm);
    expect(stub).not.toContain("faltó en");
  });
});
