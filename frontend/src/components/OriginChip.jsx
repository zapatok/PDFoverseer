import Badge from "../ui/Badge";

const ORIGIN_VARIANT = {
  OCR:    "iris",
  R1:     "jade",
  manual: "amber",
};

export default function OriginChip({ origin }) {
  const variant = ORIGIN_VARIANT[origin] ?? "neutral";
  return <Badge variant={variant}>{origin}</Badge>;
}
