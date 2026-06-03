// Cell readiness for the honest "listo / pendiente" model (conteo-confiable A1/A3).
//
// A cell is *listo* (green) when its count is trustworthy: the scanner reported
// HIGH confidence (every file 1-page, or a fixed-page sigla, or OCR), the
// operator confirmed it by hand, or there is a manual override. Otherwise it is
// *pendiente* (amber) — R1 sin verificar. compilation_suspect no longer decides
// the dot; a multi-page cell is already LOW confidence -> amber.

export function hasOverride(cell) {
  // 0 is a valid override (discard a file's contribution) — guard on presence.
  return cell?.user_override !== null && cell?.user_override !== undefined;
}

export function isCellReady(cell) {
  return cell?.confidence === "high" || !!cell?.confirmed || hasOverride(cell);
}

// Dot tone. Scanning/error take precedence; a cell with no data yet stays
// neutral (gray) so a fresh, unscanned month doesn't read as all-pendiente.
export function dotVariantFor(cell, { isScanning = false } = {}) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (!cell) return "neutral";
  return isCellReady(cell) ? "confidence-high" : "confidence-low";
}
