// Pure helpers for the viewer reorg-mode range selection (1-based, inclusive).
export function isValidRange(start, end, totalPages) {
  if (start == null || end == null) return false;
  return Number.isInteger(start) && Number.isInteger(end)
    && start >= 1 && end <= totalPages && start <= end;
}

export function normalizeRange(a, b) {
  return a <= b ? [a, b] : [b, a];
}

/**
 * Pure reducer for the reorg viewer's keyboard range marking (`[` `]`
 * `Escape` — Track D §4). Shared by the keyboard handler AND the mouse
 * "Marcar inicio/fin" buttons (WorkerCountViewer.jsx) so both input methods
 * stay in sync (single source of truth).
 *
 * Each key always writes its OWN slot (`[`→start, `]`→end) at the current
 * page, whichever key was actually pressed — it does NOT swap the pair when
 * the operator marks them out of order (start ends up > end). Swapping in
 * place would mislabel which page the operator just marked (e.g. pressing
 * `[` at page 4 could make the HUD show "Fin: pág. 4" instead of "Inicio:
 * pág. 4" — confusing). Order-normalization for VALIDITY/creation already
 * exists one layer up via `normalizeRange`/`isValidRange` (used by
 * `ReorgHud`'s `rangeValid` and `handleCreate`) — an out-of-order pair marked
 * here is still a valid range once normalized there.
 *
 * @param {"["|"]"|"Escape"} key
 * @param {{start: number|null, end: number|null}} range - current marked bounds.
 * @param {number} currentPage - the page the viewer is on when the key fires.
 * @returns {{start: number|null, end: number|null}} the next range; unknown
 *   keys return the SAME `range` reference unchanged (no-op).
 */
export function applyRangeKey(key, range, currentPage) {
  if (key === "Escape") return { start: null, end: null };
  if (key === "[") return { start: currentPage, end: range.end };
  if (key === "]") return { start: range.start, end: currentPage };
  return range;
}
