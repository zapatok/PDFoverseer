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

export function isCellReady(cell) {
  if (!!cell?.confirmed || hasOverride(cell)) return true;
  // Backend all_reliable (Incr 2) is authoritative; fall back to the 1B proxy
  // (allFilesReliable) for cells not yet migrated (e.g. MAYO scanned pre-Incr-2).
  return cell?.all_reliable ?? allFilesReliable(cell);
}

// Dot tone. Scanning/error take precedence; a cell with no data yet stays
// neutral (gray) so a fresh, unscanned month doesn't read as all-pendiente.
export function dotVariantFor(cell, { isScanning = false } = {}) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (!cell) return "neutral";
  return isCellReady(cell) ? "confidence-high" : "confidence-low";
}
