const VARIANTS = {
  "confidence-high": "bg-po-dot-high",
  "confidence-low":  "bg-po-dot-low",
  "state-suspect":   "bg-po-dot-suspect",
  "state-scanning":  "bg-po-dot-scanning animate-pulse",
  "state-error":     "bg-po-dot-error",
  "state-override":  "bg-po-dot-override",
  "neutral":         "bg-po-text-subtle",
};

export default function Dot({ variant = "neutral", className = "" }) {
  return (
    <span
      aria-hidden="true"
      className={[
        "inline-block h-2 w-2 rounded-full shrink-0",
        VARIANTS[variant],
        className,
      ].join(" ")}
    />
  );
}
