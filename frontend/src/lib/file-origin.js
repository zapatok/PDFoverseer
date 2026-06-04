// Pure, node-testable helpers for the FileList "Archivos" column.

// G2 — what to show in the per-file doc-count cell. A "Pendiente" file has not
// been counted yet, so it reads as "—" (still editable). A "Revisar" file was
// scanned and read 0 — that 0 is a real count, shown as-is. Everyone else shows
// their effective count (default 1 when absent).
export function fileCountDisplay(origin, effectiveCount) {
  if (origin === "Pendiente") return { value: null, placeholder: "—" };
  return {
    value: effectiveCount ?? (origin === "Revisar" ? 0 : 1),
    placeholder: undefined,
  };
}

// G3 — precedence for the per-file rows: most-urgent first. Unknown origins last.
export const ORIGIN_RANK = {
  Error: 0,
  Pendiente: 1,
  Revisar: 2,
  Manual: 3,
  OCR: 4,
  R1: 5,
};

export function compareByOrigin(a, b) {
  const ra = ORIGIN_RANK[a.origin] ?? 99;
  const rb = ORIGIN_RANK[b.origin] ?? 99;
  if (ra !== rb) return ra - rb;
  return (a.name ?? "").localeCompare(b.name ?? "");
}
