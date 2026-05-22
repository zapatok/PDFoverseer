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

  it("fija min_match al número de anclas coincidentes", () => {
    const stub = buildFlavorStub(NM);
    expect(stub).toContain("min_match=2,");
  });

  it("sin anclas faltantes no aparecen líneas de anclas comentadas", () => {
    const nm = { ...NM, missing_anchors: [] };
    const stub = buildFlavorStub(nm);
    expect(stub).not.toContain("faltó en");
  });
});
