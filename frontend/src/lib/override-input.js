// Validation for the manual-override field (Incr 1B, Decisión 4 partial).
// Negatives are rejected; 0 is a valid override; empty clears it. The ≤páginas
// cap (Incr 2) lives here via maxPages: an over-cap integer comes back flagged
// as overCap — not plain invalid — so callers can offer the allow_over_pages
// confirmation instead of a mute refusal.

export function parseOverrideInput(raw, { maxPages = null } = {}) {
  if (raw === "" || raw === null || raw === undefined) {
    return { value: null, valid: true };
  }
  // Number (not parseInt): parseInt("5abc") → 5 silently; Number("5abc") → NaN.
  // Require a non-negative integer — a document count is never fractional.
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 0) {
    return { value: null, valid: false };
  }
  if (maxPages != null && n > maxPages) {
    // Over-cap is NOT garbage: the value parses, it just exceeds the pages.
    // Callers surface a confirmation (allow_over_pages) instead of refusing.
    return { value: n, valid: false, overCap: true };
  }
  return { value: n, valid: true };
}
