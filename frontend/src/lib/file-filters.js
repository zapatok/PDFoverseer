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
