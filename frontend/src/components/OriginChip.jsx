import Badge from "../ui/Badge";

export const ORIGIN_VARIANT = {
  OCR:        "iris",
  R1:         "jade",
  manual:     "amber",
  Estructura: "blue", // page_count_pure — counted by document structure, no OCR
};

// Pure mapping helper (node-env testable): unknown origins fall back to neutral.
export function originVariant(origin) {
  return ORIGIN_VARIANT[origin] ?? "neutral";
}

export default function OriginChip({ origin }) {
  return <Badge variant={originVariant(origin)}>{origin}</Badge>;
}
