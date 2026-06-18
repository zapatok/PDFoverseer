// Pure helpers for the viewer reorg-mode range selection (1-based, inclusive).
export function isValidRange(start, end, totalPages) {
  if (start == null || end == null) return false;
  return Number.isInteger(start) && Number.isInteger(end)
    && start >= 1 && end <= totalPages && start <= end;
}

export function normalizeRange(a, b) {
  return a <= b ? [a, b] : [b, a];
}
