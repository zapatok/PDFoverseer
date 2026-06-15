// Validation for the manual-override field (Incr 1B, Decisión 4 partial).
// Negatives are rejected; 0 is a valid override; empty clears it. The ≤páginas
// cap is intentionally NOT here (deferred to Incr 2 with persisted per_file_pages).

export function parseOverrideInput(raw) {
  if (raw === "" || raw === null || raw === undefined) {
    return { value: null, valid: true };
  }
  const n = parseInt(raw, 10);
  if (Number.isNaN(n) || n < 0) {
    return { value: null, valid: false };
  }
  return { value: n, valid: true };
}
