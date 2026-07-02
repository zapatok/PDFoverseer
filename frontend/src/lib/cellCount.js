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

// Mirror fiel de core/cell_count.py::_sum_marks. Suma los `count` de worker_marks
// filtrando a los archivos presentes. presentFiles: Array|Set|null.
//   - no-null (incluido [] vacío) → filtra por ese conjunto (huérfanos descartados;
//     vacío explícito ⇒ 0). NO reusar computeWorkerCount: su [] significa "no filtrar".
//   - null → legacy: filtra por las claves de per_file si no está vacío; si no, suma todo.
export function _sumMarks(cell, presentFiles = null) {
  const marks = cell?.worker_marks ?? {};
  let allowed;
  let filterOn;
  if (presentFiles != null) {
    allowed = new Set(presentFiles);
    filterOn = true;
  } else {
    const perFile = cell?.per_file ?? {};
    allowed = new Set(Object.keys(perFile));
    filterOn = allowed.size > 0;
  }
  let total = 0;
  for (const [filename, pageMarks] of Object.entries(marks)) {
    if (filterOn && !allowed.has(filename)) continue;
    for (const m of pageMarks ?? []) {
      if (m && typeof m.count === "number") total += m.count;
    }
  }
  return total;
}

// count_type === "checks" (maquinaria) → la cuenta es el tally de chequeos
// (_sumMarks), no la cascada de documentos. user_override sigue ganando.
// Incr J: + reorg_doc_delta additive on top of every base path.
function _baseCount(cell, countType = "documents", presentFiles = null) {
  if (cell?.user_override != null) return cell.user_override;
  if (countType === "checks") return _sumMarks(cell, presentFiles);
  return computeFilesCount(cell);
}

export function computeCellCount(cell, countType = "documents", presentFiles = null) {
  // F5: clamp at 0 — a reorg delta can never drive the effective count negative.
  return Math.max(0, _baseCount(cell, countType, presentFiles) + (cell?.reorg_doc_delta ?? 0));
}
