/**
 * Parse an "Ir a página" input: integer clamped to [1, pageCount]; null if unusable.
 *
 * Deviation from the naive `Number(raw)` version: `Number("")` is `0`, which
 * IS an integer, so an empty string would otherwise silently resolve to page
 * 1 instead of being rejected — guarded with an explicit blank-string check.
 */
export function parseGoToPage(raw, pageCount) {
  if (typeof raw !== "string" || raw.trim() === "") return null;
  const n = Number(raw);
  if (!Number.isInteger(n) || pageCount < 1) return null;
  return Math.min(Math.max(n, 1), pageCount);
}
