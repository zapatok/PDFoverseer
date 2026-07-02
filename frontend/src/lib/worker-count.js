import { _sumMarks } from "./cellCount";

/**
 * Suma cruda de los `count` de las marcas de los archivos en `fileNames`.
 *
 * OJO — semántica de filtro (distinta de `cellWorkerCount`): un `fileNames`
 * vacío o nulo significa "NO filtrar" (cuenta todas las marcas), no "filtrar
 * todo". Por eso SOLO es seguro llamarla con una lista REAL de archivos
 * presentes (nunca `null`/`[]` como sustituto de "sin datos"). Hoy su único
 * consumidor es `WorkerCountViewer`, que siempre le pasa `files.map(f => f.name)`
 * tras haber cargado los PDFs de la celda.
 *
 * Para el total canónico de una celda (con filtro de huérfanas por per_file y el
 * delta de reorg) usa `cellWorkerCount`, no esta función.
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
 * Total de trabajadores de una celda: espejo FIEL de
 * `core/cell_count.py::compute_worker_count`. Delega la suma filtrada en
 * `_sumMarks` (mismo helper que usa el conteo de documentos) para que la única
 * fuente del filtro viva en `cellCount.js` — no una copia divergente (bug #2/F1):
 *
 *   - `fileNames` no-nulo (incluido `[]` vacío) → filtra por ese conjunto de
 *     archivos presentes; las marcas huérfanas (PDF renombrado/borrado) se
 *     descartan; `[]` explícito ⇒ 0.
 *   - `fileNames` nulo → comportamiento legacy: filtra por las claves de
 *     `per_file` si no está vacío; si no, suma todo. Este es el fallback que usa
 *     `DetailPanel` cuando el backend aún no envió `worker_count` en el store.
 *
 * Suma además el delta de reorganización (`reorg_worker_delta`, Incr J) y acota
 * el total a 0 (F5) — el delta nunca deja el total negativo. Los subtotales por
 * archivo (`fileSubtotal`) siguen crudos: el delta es a nivel de celda.
 *
 * @param {object} cell   - objeto de celda del store (puede ser null/undefined)
 * @param {string[]|null} fileNames - nombres de los PDFs presentes hoy, o null.
 * @returns {number}
 */
export function cellWorkerCount(cell, fileNames) {
  return Math.max(0, _sumMarks(cell, fileNames) + (cell?.reorg_worker_delta ?? 0));
}
