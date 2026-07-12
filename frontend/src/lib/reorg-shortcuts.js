/**
 * Fuente única de los atajos del modo reorganización del visor (Track D §4).
 * Espejo de `worker-shortcuts.js`: misma forma (`keys`/`match`/`action`), pero
 * para el marcado de rango por teclado en vez del conteo de trabajadores. La
 * leyenda (ReorgHud, en WorkerCountViewer.jsx) y el handler de teclado
 * (WorkerCountViewer.jsx, rama `mode === "reorg"`) se mantienen alineados con
 * esta lista; el test de cobertura verifica que cada `match` esté cubierto
 * por el handler.
 *
 * - `keys`:  etiquetas mostradas como chips.
 * - `match`: valores de `KeyboardEvent.key` que disparan el atajo (para el test).
 * - `action`: descripción en español neutro.
 */
export const REORG_SHORTCUTS = [
  { keys: ["["],     match: ["["],      action: "Marcar inicio" },
  { keys: ["]"],     match: ["]"],      action: "Marcar fin" },
  { keys: ["Enter"], match: ["Enter"],  action: "Crear operación" },
  { keys: ["Esc"],   match: ["Escape"], action: "Limpiar selección" },
];
