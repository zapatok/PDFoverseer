/**
 * Escala para que una página quepa COMPLETA (contain) dentro de un panel.
 *
 * @param {{width:number,height:number}} viewport - tamaño de la página a escala 1.
 * @param {{width:number,height:number}} panel - tamaño disponible del panel.
 * @returns {number} factor de escala; 1 si alguna dimensión es <= 0 (degenerado).
 */
export function computeFitScale(viewport, panel) {
  const pw = viewport?.width || 0;
  const ph = viewport?.height || 0;
  const cw = panel?.width || 0;
  const ch = panel?.height || 0;
  if (pw <= 0 || ph <= 0 || cw <= 0 || ch <= 0) return 1;
  return Math.min(cw / pw, ch / ph);
}
