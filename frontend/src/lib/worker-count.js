/**
 * Total de trabajadores de una celda: suma de los `count` de todas las marcas
 * de los archivos presentes en `fileNames`. Espejo en JS de compute_worker_count
 * del backend (api/state.py): las marcas de archivos ausentes (renombrados o
 * eliminados) no se cuentan. Si `fileNames` viene vacío o nulo NO se filtra
 * (celda sin escanear) — espeja a `compute_worker_count`, que no filtra cuando
 * `per_file` está vacío. Ojo: un array vacío es truthy en JS, así que el guard
 * comprueba la longitud explícitamente.
 *
 * @param {object} marks - { filename: [{page, count}, ...] }
 * @param {string[]} fileNames - nombres de los PDFs presentes hoy en la celda.
 * @returns {number}
 */
export function computeWorkerCount(marks, fileNames) {
  const filter = Array.isArray(fileNames) && fileNames.length > 0;
  const present = new Set(fileNames || []);
  let total = 0;
  for (const [filename, pageMarks] of Object.entries(marks || {})) {
    if (filter && !present.has(filename)) continue;
    for (const m of pageMarks || []) {
      if (m && typeof m.count === "number") total += m.count;
    }
  }
  return total;
}

/** Subtotal de un solo archivo: suma de los `count` de sus marcas. */
export function fileSubtotal(marks, filename) {
  let total = 0;
  for (const m of marks?.[filename] || []) {
    if (m && typeof m.count === "number") total += m.count;
  }
  return total;
}

/**
 * Total de trabajadores de la celda, incluyendo el delta de reorganización
 * de Incr J (`reorg_worker_delta`). Los subtotales por archivo (fileSubtotal)
 * siguen siendo crudos — el delta es una cantidad a nivel de celda, no
 * por archivo.
 *
 * Espeja el patrón base+delta de cellCount.js.
 *
 * @param {object} cell   - objeto de celda del store (puede ser null/undefined)
 * @param {string[]} fileNames - nombres de los PDFs presentes hoy en la celda
 * @returns {number}
 */
export function cellWorkerCount(cell, fileNames) {
  // F5: clamp at 0 — a reorg delta can never drive the worker total negative.
  return Math.max(
    0,
    computeWorkerCount(cell?.worker_marks ?? {}, fileNames) + (cell?.reorg_worker_delta ?? 0),
  );
}
