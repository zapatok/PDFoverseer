// Opciones de rotación para ops "rotate" (ReorgHud del visor + ReorgMenu de
// FileList). Grados en sentido HORARIO — la misma convención que /Rotate de
// PDF y getViewport de pdf.js, así lo que se previsualiza es lo que paso-1
// aplica físicamente.
//
// Invariante (pinneada por test): DEFAULT_ROTATION_DEG es una de las opciones.
// El bug original: el estado inicial era 0 pero el <select> solo ofrecía
// 90/180/270 — el usuario veía una opción "elegida" y la op viajaba con
// rotation_deg 0 (un no-op silencioso).

export const ROTATION_OPTIONS = [
  { value: 90, label: "90° a la derecha ⟳" },
  { value: 180, label: "180°" },
  { value: 270, label: "90° a la izquierda ⟲" },
];

export const DEFAULT_ROTATION_DEG = 90;
