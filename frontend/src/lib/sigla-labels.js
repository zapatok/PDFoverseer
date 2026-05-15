// Source of truth: core/domain.py CATEGORY_FOLDERS. Do NOT fabricate domain
// meaning — folder name IS the label (prefix N.- stripped, tildes added).
// Acronyms (ART, ODI, IRL, PTS, CHPS) stay as-is — Daniel uses them.
//
// If a label reads awkwardly in tooltips/Detail header, ASK Daniel before
// changing it. Don't expand acronyms unilaterally.
export const SIGLA_LABELS = {
  reunion: "Reunión de prevención",
  irl: "Inducción IRL",
  odi: "ODI Visitas",
  charla: "Charlas",
  chintegral: "Charla integral",
  dif_pts: "Difusión PTS",
  art: "ART",
  insgral: "Inspecciones generales",
  bodega: "Inspección bodega",
  maquinaria: "Inspección de maquinaria",
  ext: "Extintores",
  senal: "Señaléticas",
  exc: "Excavaciones y vanos",
  altura: "Trabajos en altura",
  caliente: "Inspección trabajos en caliente",
  herramientas_elec: "Inspección herramientas eléctricas",
  andamios: "Andamios",
  chps: "CHPS",
};

// Canonical sigla order — the 18 categories in the order they appear in the
// monthly Excel. Single source of truth for HospitalCard, HospitalDetail
// and SparkGrid.
export const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts",
  "art", "insgral", "bodega", "maquinaria", "ext", "senal",
  "exc", "altura", "caliente", "herramientas_elec", "andamios", "chps",
];
