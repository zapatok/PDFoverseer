// Cost estimation for the pase-2 OCR guard (audit finding #2). The backend is
// the source of truth for the exact PDF count (returned as total_pdfs once a
// scan launches), but the guard must decide BEFORE launching, so it estimates
// from what the client already holds.

import { computeCellCount } from "./cellCount";
import { OCR_EST_SECONDS_PER_PDF } from "./constants";

export function estimateScanSeconds(totalPdfs) {
  return totalPdfs * OCR_EST_SECONDS_PER_PDF;
}

export function shouldConfirmScan(totalPdfs, threshold) {
  return totalPdfs > threshold;
}

/**
 * Human-facing scan ETA in whole minutes (review #11). OCR scans run minutes,
 * not seconds, so a seconds readout churns distractingly; round to minutes and
 * never show 0 (a running scan always takes "at least a minute" to the eye).
 */
export function formatEta(ms) {
  return `~${Math.max(1, Math.round(ms / 60000))} min`;
}

/**
 * Best client-side proxy for the number of PDFs an OCR scan will process: the
 * pase-1 filename count (≈ sigla-matching PDFs in the cell folder). For the
 * cells the guard actually targets — many-PDF regime-1 categories like
 * HPV/art (767 PDFs) — filename_count equals the scan size. Falls back to the
 * displayed document count, then 0. (pdf_count_hint is transient backend folder
 * info and is not serialized into the session state, so it can't be used here.)
 */
export function totalPdfsForPairs(sessionState, pairs) {
  const cells = sessionState?.cells ?? {};
  let total = 0;
  for (const [hosp, sigla] of pairs ?? []) {
    const cell = cells?.[hosp]?.[sigla];
    if (!cell) continue;
    total += cell.filename_count ?? computeCellCount(cell) ?? 0;
  }
  return total;
}
