// Mirror of api/state.py:compute_cell_count. Mantener en sync — ambas funciones
// deben producir el mismo número para el mismo cell. Cross-language parity
// validada por tests/fixtures/cell_count_cases.json (Python tests + smoke).
// Spec FASE 4 §6.2.

export function computeCellCount(cell) {
  if (cell?.user_override != null) return cell.user_override;

  const perFile = cell?.per_file ?? {};
  const perFileOverrides = cell?.per_file_overrides ?? {};
  const hasPerFile = perFile && Object.keys(perFile).length > 0;
  const hasOverrides = perFileOverrides && Object.keys(perFileOverrides).length > 0;

  if (hasPerFile || hasOverrides) {
    const allFiles = new Set([
      ...Object.keys(perFile ?? {}),
      ...Object.keys(perFileOverrides ?? {}),
    ]);
    let sum = 0;
    for (const f of allFiles) {
      const val = perFileOverrides?.[f] ?? perFile?.[f] ?? 0;
      sum += val;
    }
    return sum;
  }

  return cell?.ocr_count ?? cell?.filename_count ?? 0;
}
