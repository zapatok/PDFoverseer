// Mirror of api/state.py:compute_cell_count. Mantener en sync — ambas funciones
// deben producir el mismo número para el mismo cell. Cross-language parity
// validada por tests/fixtures/cell_count_cases.json (Python tests + smoke).
// Spec FASE 4 §6.2. Incr 1B: extraído computeFilesCount (suma por archivos sin
// el override de celda) para el toggle "archivos: N" — misma lógica de suma.

export function computeFilesCount(cell) {
  const perFile = cell?.per_file ?? {};
  const perFileOverrides = cell?.per_file_overrides ?? {};
  const hasPerFile = Object.keys(perFile).length > 0;
  const hasOverrides = Object.keys(perFileOverrides).length > 0;

  if (hasPerFile || hasOverrides) {
    const allFiles = new Set([
      ...Object.keys(perFile),
      ...Object.keys(perFileOverrides),
    ]);
    let sum = 0;
    for (const f of allFiles) {
      sum += perFileOverrides[f] ?? perFile[f] ?? 0;
    }
    return sum;
  }

  return cell?.ocr_count ?? cell?.filename_count ?? 0;
}

export function computeCellCount(cell) {
  if (cell?.user_override != null) return cell.user_override;
  return computeFilesCount(cell);
}
