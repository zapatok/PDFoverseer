export const CTA_LLENAR_MANUAL = "Llenar manualmente →";

// Cost guard for pase-2 OCR (audit finding #2). Single-user/LAN app, so these
// are UX thresholds, not hard limits: warn before launching a long OCR run and
// remind that regime-1 cells are already counted by filename.
export const OCR_CONFIRM_PDF_THRESHOLD = 50; // ask to confirm above this many PDFs
// Recalibrated post-threading (2026-07-11, §A5): ~0.35 s/page × ~3 pages
// average ≈ 1 s/PDF. The old value (4) predated OCR_PAGE_THREADS and
// over-estimated ETAs by ~4x ("~51 min" for a scan that took ~13). Still
// orientative by design, not a hard guarantee.
export const OCR_EST_SECONDS_PER_PDF = 1;
