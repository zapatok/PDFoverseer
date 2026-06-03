/**
 * Fuente única de los atajos del visor de conteo de trabajadores. La leyenda
 * (WorkerHud) y el handler de teclado (WorkerCountViewer) se mantienen alineados
 * con esta lista; el test verifica que cada `match` esté cubierto por el handler.
 *
 * - `keys`:  etiquetas mostradas como chips.
 * - `match`: valores de `KeyboardEvent.key` que disparan el atajo (para el test).
 * - `action`: descripción en español neutro.
 */
export const WORKER_SHORTCUTS = [
  { keys: ["0-9"],        match: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], action: "Ingresar número" },
  { keys: ["Av Pág"],     match: ["PageDown"],         action: "Fijar y avanzar" },
  { keys: ["Re Pág"],     match: ["PageUp"],           action: "Retroceder" },
  { keys: ["Supr"],       match: ["Delete"],           action: "Borrar marca" },
  { keys: ["E"],          match: ["e", "E"],           action: "Editar página" },
  { keys: ["+", "−"],     match: ["+", "=", "-", "_"], action: "Acercar / alejar" },
  { keys: ["M"],          match: ["m", "M"],           action: "Voz on / off" },
  { keys: ["Retroceso"],  match: ["Backspace"],        action: "Corregir dígito" },
];
