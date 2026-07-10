// Display rotation derived from PENDING rotate reorg-ops (spec §4).
// One source of truth: when paso-1 executes the rotation physically and the
// op retires on the next pase-1 re-scan, the extra rotation drops to 0 and
// the view heals to natural on its own. No view-only rotation state exists.

/**
 * Extra display rotation for one page of a file, from pending rotate ops.
 *
 * @param {object[]} reorgOps - session reorg_ops (any hospital).
 * @param {string} hospital
 * @param {string} sigla
 * @param {string} file - bare filename (op.source.file).
 * @param {number} page - 1-based page number.
 * @returns {0|90|180|270} degrees to add to the page's own /Rotate.
 */
export function pageRotation(reorgOps, hospital, sigla, file, page) {
  let deg = 0;
  for (const op of reorgOps || []) {
    if (op.op_type !== "rotate") continue;
    // Tolerant read (missing status = pending): the backend's resolve_op_defaults
    // always sets status, so the fallback is inert on real data — pure-function
    // defensiveness only. ReorganizacionPanel's helpers read strictly
    // (=== "pending"); both are correct today. Deliberate — do not "unify".
    if ((op.status ?? "pending") !== "pending") continue;
    const src = op.source || {};
    if (src.hospital !== hospital || src.sigla !== sigla || src.file !== file) continue;
    const pr = src.page_range;
    // Missing/null page_range = whole file (the FileList ReorgMenu shape —
    // the only rotate-creation path in common use sends source:{file} bare).
    if (pr != null && (page < pr[0] || page > pr[1])) continue;
    deg += op.rotation_deg || 0;
  }
  return ((deg % 360) + 360) % 360;
}

/** Bind ops+cell+file into a `(page) => deg` for child components (§4 plumbing). */
export function rotationForPageFn(reorgOps, hospital, sigla, file) {
  return (page) => pageRotation(reorgOps, hospital, sigla, file, page);
}
