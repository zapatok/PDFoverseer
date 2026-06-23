// Per-sigla reference card (rev-2 §6): a short "what is this document type" line
// plus the typical page-count band. Descriptions are Daniel-reviewed (spec §6.2);
// page ranges are the p25–p75 band from tools/audit_sigla_page_ranges.py over the
// real ABRIL/FEBRERO/MARZO corpus (robust to outliers like a 677-page charla).

export const SIGLA_DESCRIPTION = {
  reunion: "Acta de reunión del equipo/comité de prevención.",
  irl: "Información de Riesgos Laborales entregada al trabajador (DS 44).",
  odi: "Obligación de Informar a visitas: riesgos de la obra para quien la visita.",
  charla: "Charla de seguridad con su lista de asistencia.",
  chintegral: "Charla integral con lista de asistencia ampliada.",
  dif_pts: "Difusión de un Procedimiento de Trabajo Seguro.",
  art: "Análisis de Riesgo del Trabajo, por tarea.",
  insgral: "Inspección general de las condiciones de la obra.",
  bodega: "Inspección de la bodega (orden, almacenamiento).",
  maquinaria: "Inspección del estado de maquinaria.",
  ext: "Registro/inspección de extintores.",
  senal: "Inspección de señaléticas de la obra.",
  revdocmaq: "Revisión de la documentación de la maquinaria.",
  exc: "Chequeo de excavaciones y vanos.",
  altura: "Chequeo/permiso de trabajos en altura.",
  caliente: "Chequeo/permiso de trabajos en caliente.",
  espacios: "Inspección de seguridad para trabajos en espacios confinados.",
  herramientas_elec: "Inspección de herramientas eléctricas.",
  andamios: "Lista de chequeo de andamios.",
  chps: "Acta del Comité Paritario de Higiene y Seguridad.",
};

// p25–p75 page-count band per sigla (from the corpus audit).
export const SIGLA_PAGE_RANGE = {
  reunion: { p25: 2, p75: 3 },
  irl: { p25: 40, p75: 48 },
  odi: { p25: 2, p75: 2 },
  charla: { p25: 2, p75: 2 },
  chintegral: { p25: 5, p75: 8 },
  dif_pts: { p25: 10, p75: 10 },
  art: { p25: 4, p75: 5 },
  insgral: { p25: 1, p75: 2 },
  bodega: { p25: 1, p75: 2 },
  maquinaria: { p25: 2, p75: 8 },
  ext: { p25: 1, p75: 5 },
  senal: { p25: 4, p75: 6 },
  revdocmaq: { p25: 1, p75: 2 },
  exc: { p25: 5, p75: 21 },
  altura: { p25: 1, p75: 3 },
  caliente: { p25: 1, p75: 2 },
  espacios: { p25: 2, p75: 2 },
  herramientas_elec: { p25: 1, p75: 1 },
  andamios: { p25: 1, p75: 3 },
  chps: { p25: 3, p75: 3 },
};

// Mirror of core/scanners/patterns.py::COUNT_TYPE_BY_SIGLA. Must stay verbatim
// in sync — 20 entries, same values. Verified by sigla-info.test.js (completeness gate).
// countTypeFor fallback = "documents" so future siglas added to the backend before
// the JS mirror is updated degrade gracefully rather than break.
export const SIGLA_COUNT_TYPE = {
  reunion: "documents",
  art: "documents",
  irl: "documents",
  odi: "documents",
  charla: "documents_workers",
  insgral: "documents",
  bodega: "documents",
  caliente: "documents",
  exc: "documents",
  senal: "documents",
  ext: "documents",
  maquinaria: "checks",
  altura: "documents",
  chps: "documents",
  chintegral: "documents_workers",
  dif_pts: "documents_workers",
  herramientas_elec: "documents",
  andamios: "documents",
  revdocmaq: "documents",
  espacios: "documents",
};

export const countTypeFor = (sigla) => SIGLA_COUNT_TYPE[sigla] ?? "documents";

export function formatPageRange(range) {
  if (!range) return "";
  const { p25, p75 } = range;
  if (p25 === p75) {
    return p25 === 1 ? "Normalmente 1 página." : `Suele tener ${p25} páginas.`;
  }
  return `Suele tener ${p25}–${p75} páginas por documento.`;
}
