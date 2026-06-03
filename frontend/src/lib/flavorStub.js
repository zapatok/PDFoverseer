/**
 * flavorStub — genera un stub de flavor para patterns.py a partir de un
 * NearMatchEntry (A14). El stub se copia al portapapeles para que el
 * desarrollador lo pegue directamente en patterns.py.
 *
 * El stub sigue la convención de nombres A9 y la estructura de anchors A12.
 */

/**
 * Construye el texto del stub de flavor para patterns.py.
 *
 * @param {object} nm - NearMatchEntry serializado.
 * @param {string} nm.pdf_name - Nombre del PDF donde apareció el candidato.
 * @param {number} nm.page_index - Índice de página (0-based).
 * @param {string} nm.flavor_name - Flavor más cercano (para orientar el nombre del nuevo).
 * @param {string[]} nm.matched_anchors - Anclas que coincidieron.
 * @param {string[]} nm.missing_anchors - Anclas que faltaron.
 * @returns {string} Texto del stub listo para pegar en patterns.py.
 */
export function buildFlavorStub(nm) {
  const matched = nm.matched_anchors
    .map((a) => `            "${a}",`)
    .join("\n");
  const missing = nm.missing_anchors
    .map((a) => `            # "${a}",  # faltó en ${nm.pdf_name} p.${nm.page_index + 1}`)
    .join("\n");

  return `        # --- NUEVO FLAVOR (candidato desde casi-match en ${nm.pdf_name} p.${nm.page_index + 1}) ---
        # Basado en: ${nm.flavor_name}
        Flavor(
            name="nuevo_flavor",
            anchors=[
${matched}
${missing}
            ],
            anti_anchors=[],
            min_match=${Math.max(3, nm.matched_anchors.length)},
        ),`;
}

/**
 * Copia el stub de flavor al portapapeles del navegador.
 *
 * @param {object} nm - NearMatchEntry serializado.
 * @returns {Promise<void>}
 */
export async function copyFlavorStub(nm) {
  const text = buildFlavorStub(nm);
  await navigator.clipboard.writeText(text);
}
