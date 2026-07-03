export const CTA_LLENAR_MANUAL = "Llenar manualmente →";

// Cost guard for pase-2 OCR (audit finding #2). Single-user/LAN app, so these
// are UX thresholds, not hard limits: warn before launching a long OCR run and
// remind that regime-1 cells are already counted by filename.
export const OCR_CONFIRM_PDF_THRESHOLD = 50; // ask to confirm above this many PDFs
export const OCR_EST_SECONDS_PER_PDF = 4; // rough ETA basis for the dialog
