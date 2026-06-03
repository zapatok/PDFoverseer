// Brief, operator-facing explanation per ScanResult.method token (review #8).
// Shown behind an (i) tooltip next to the Método row. Keep each line short and
// in plain Spanish — what the method counts, not how it works internally.
// Invariant (method-info.test.js): every token in METHOD_LABEL has an entry here.
export const METHOD_INFO = {
  filename_glob: "Un documento por archivo PDF. Fiable cuando cada PDF es un solo documento.",
  page_count_pure: "Un documento por página. Para siglas donde cada página es un chequeo (bodega, extintores, excavaciones…).",
  header_detect: "Lee el encabezado de cada página y cuenta una portada por documento.",
  header_band_anchors: "Lee el encabezado de cada página y cuenta una portada por documento.",
  corner_count: "Cuenta documentos por la numeración de página detectada por OCR.",
  v4: "Cuenta documentos por la numeración 'Página N de M' detectada por OCR.",
  manual: "Valor ingresado a mano por el operador.",
};
