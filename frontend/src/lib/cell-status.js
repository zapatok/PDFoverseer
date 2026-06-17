import { countTypeFor } from "./sigla-info";

// Cell readiness for the honest "listo / pendiente" model (Incr 1B, Decisión 1).
//
// A cell is *listo* (green) when its count is trustworthy by PROVENANCE, not by
// the scanner's `confidence` alone: the operator confirmed it, there is a
// cell-level manual override, OR every file is reliable (R1 / Manual). Any file
// counted by OCR (without a per-file override), Pendiente, or Error keeps the
// cell *pendiente* (amber) until a human confirms it.
//
// OCR_METHODS mirrors the OCR/Revisar branch of `_origin_for`
// (api/routes/sessions.py): these per-file methods read uncertain values.
// `page_count_pure` is intentionally NOT here — it maps to R1 (reliable
// fixed-page path); adding it would wrongly amber fixed-page siglas.
export const OCR_METHODS = new Set([
  "header_detect",
  "corner_count",
  "header_band_anchors",
  "v4",
]);

// Incr 2 — count_types whose document override caps at ≤ pages (Decisión 4).
// `checks` (maquinaria) is exempt. Shared by DetailPanel + FileList (no drift).
export const CAPPED_COUNT_TYPES = ["documents", "documents_workers"];

export function isCappedCountType(countType) {
  return CAPPED_COUNT_TYPES.includes(countType);
}

export function hasOverride(cell) {
  // 0 is a valid override (discard a file's contribution) — guard on presence.
  return cell?.user_override !== null && cell?.user_override !== undefined;
}

// True when at least one file was counted by OCR and has NOT been corrected by a
// per-file override. A per-file override turns that file into "Manual" (reliable).
export function anyUnreliableOcrFile(cell) {
  const methods = cell?.per_file_method ?? {};
  const overrides = cell?.per_file_overrides ?? {};
  for (const [filename, method] of Object.entries(methods)) {
    if (OCR_METHODS.has(method) && overrides[filename] === undefined) {
      return true;
    }
  }
  return false;
}

// Every file is R1 or Manual. `confidence === "high"` already guarantees every
// filename_glob file is single-page (simple_factory.py:84/97); the OCR exclusion
// is what this layer adds on top.
export function allFilesReliable(cell) {
  return cell?.confidence === "high" && !anyUnreliableOcrFile(cell);
}

// countType = "checks" (maquinaria): ready iff the operator marked it terminado
// via the counter viewer (human verification, no OCR/filename involved).
// For all other count types, the standard provenance cascade applies.
export function isCellReady(cell, countType = "documents") {
  if (cell?.note_status === "por_resolver") return false;
  if (!!cell?.confirmed || hasOverride(cell)) return true;
  if (countType === "checks") return cell?.worker_status === "terminado";
  // Backend all_reliable (Incr 2) is authoritative; fall back to the 1B proxy
  // (allFilesReliable) for cells not yet migrated (e.g. MAYO scanned pre-Incr-2).
  return cell?.all_reliable ?? allFilesReliable(cell);
}

// Incr 3B: which DetailPanel counting module a cell's count_type implies.
// The worker/checks counter shows for documents_workers (charla/chintegral/dif_pts)
// and checks (maquinaria); plain documents siglas show only the document controls.
export const showsWorkerCounter = (countType) =>
  countType === "checks" || countType === "documents_workers";

// Dot tone. Scanning/error take precedence; a cell with no data yet stays
// neutral (gray) so a fresh, unscanned month doesn't read as all-pendiente.
export function dotVariantFor(cell, { isScanning = false, countType = "documents" } = {}) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (!cell) return "neutral";
  return isCellReady(cell, countType) ? "confidence-high" : "confidence-low";
}

// A worker/checks cell is "relevant" to the aggregate iff it has files.
function cellHasFiles(cell) {
  const pf = cell?.per_file;
  if (pf && Object.keys(pf).length > 0) return true;
  return (cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? 0) > 0;
}

// M2 (Incr 3C): aggregate worker-counting status across a hospital's worker cells
// (count_type ∈ {documents_workers, checks} = charla/chintegral/dif_pts/maquinaria).
// "relevant" = cell has files. Returns null if no relevant worker cells (→ no chip).
// listo = all relevant terminado; pendiente = none started; en_proceso = the rest.
export function hospitalWorkerStatus(cells) {
  if (!cells) return null;
  let total = 0;
  let done = 0;
  let started = 0;
  for (const [sigla, cell] of Object.entries(cells)) {
    if (!showsWorkerCounter(countTypeFor(sigla))) continue;
    if (!cellHasFiles(cell)) continue;
    total += 1;
    const status = cell?.worker_status;
    const hasMarks = cell?.worker_marks && Object.keys(cell.worker_marks).length > 0;
    if (status === "terminado") done += 1;
    if (status || hasMarks) started += 1;
  }
  if (total === 0) return null;
  if (done === total) return "listo";
  if (started === 0) return "pendiente";
  return "en_proceso";
}
