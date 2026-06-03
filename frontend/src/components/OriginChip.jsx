import Badge from "../ui/Badge";

// Per-file chip vocabulary (spec G1): canonical casing matches the backend
// _origin_for return values verbatim. "trivial" and "Estructura" are gone —
// a fixed-page sigla now reads as R1, a multipage filename_glob file as Pendiente.
export const ORIGIN_VARIANT = {
  R1:        "jade",
  OCR:       "iris",
  Manual:    "blue",
  Pendiente: "amber",
  Revisar:   "state-error", // OCR ran but read 0 docs (poor scan / no flavor) → manual
  Error:     "state-error",
};

// Pure mapping helper (node-env testable): unknown origins fall back to neutral.
export function originVariant(origin) {
  return ORIGIN_VARIANT[origin] ?? "neutral";
}

export default function OriginChip({ origin }) {
  return <Badge variant={originVariant(origin)}>{origin}</Badge>;
}
