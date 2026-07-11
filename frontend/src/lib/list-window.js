// Ventana virtual para listas largas de filas de altura FIJA (FileList: las
// celdas art traen ~1,300 archivos — montar 1,300 <li> con steppers/chips/menú
// congela el primer render y cada re-render). Solo se montan las filas
// visibles + overscan; dos espaciadores <li> preservan la altura total del
// scroll. Sin dependencias — la geometría es trivial porque la altura de fila
// está pinneada por estilo.

/**
 * Compute the visible slice of a fixed-row-height list.
 *
 * @param {number} scrollTop - current scrollTop of the scroll container.
 * @param {number} viewportH - visible height of the container (px).
 * @param {number} rowH - fixed row height (px).
 * @param {number} total - total row count.
 * @param {number} overscan - extra rows rendered on each side.
 * @returns {{start: number, end: number, topPad: number, bottomPad: number}}
 *   `start`/`end` = slice bounds (end exclusive); `topPad`/`bottomPad` =
 *   spacer heights in px so the scrollbar geometry matches the full list.
 */
export function computeWindow(scrollTop, viewportH, rowH, total, overscan = 8) {
  if (total <= 0) return { start: 0, end: 0, topPad: 0, bottomPad: 0 };
  const start = Math.max(0, Math.floor(scrollTop / rowH) - overscan);
  const end = Math.min(total, Math.ceil((scrollTop + viewportH) / rowH) + overscan);
  return {
    start,
    end,
    topPad: start * rowH,
    bottomPad: (total - end) * rowH,
  };
}
