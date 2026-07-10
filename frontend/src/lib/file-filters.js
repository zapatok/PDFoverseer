import { isCappedCountType } from "./cell-status";

// FileList chip filters (triage E2): search text AND origin-chip toggles.
// Empty origin selection = no origin filter (today's behavior).

export const FILTER_ORIGINS = ["R1", "RN", "OCR", "Manual", "Pendiente", "Revisar", "Error"];

/**
 * @param {{name: string, origin?: string}} file
 * @param {string} search - substring, case-insensitive, against file.name.
 * @param {string[]} activeOrigins - selected chips (empty = all).
 */
export function matchesFilters(file, search, activeOrigins) {
  if (search && !file.name.toLowerCase().includes(search.toLowerCase())) return false;
  if (activeOrigins.length > 0 && !activeOrigins.includes(file.origin ?? "R1")) return false;
  return true;
}

/** E3: subtle cue when a file's effective doc count differs from its pages.
 *  Doc-counting cells only — reuse isCappedCountType (CAPPED_COUNT_TYPES in
 *  cell-status.js exists precisely so FileList/DetailPanel don't drift;
 *  FileList already imports it). checks excluded by that same predicate. */
export function countDiffersFromPages(file, countType) {
  if (!isCappedCountType(countType)) return false;
  if (file.effective_count == null || file.page_count == null) return false;
  return file.effective_count !== file.page_count;
}
