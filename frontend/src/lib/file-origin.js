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
