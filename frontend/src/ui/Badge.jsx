const VARIANTS = {
  "confidence-high": "bg-po-confidence-high-bg text-po-confidence-high border border-po-confidence-high-border",
  "confidence-low":  "bg-po-confidence-low-bg text-po-confidence-low border border-po-confidence-low-border",
  "state-suspect":   "bg-po-suspect-bg text-po-suspect border border-po-suspect-border",
  "state-scanning":  "bg-po-scanning-bg text-po-scanning border border-po-scanning-border",
  "state-error":     "bg-po-error-bg text-po-error border border-po-error-border",
  "state-override":  "bg-po-override-bg text-po-override border border-po-override-border",
  "neutral":         "bg-po-panel-hover text-po-text-muted border border-po-border",
  // Origin variants — iris/jade/amber via existing po-* token groups
  "iris":            "bg-po-override-bg text-po-override border border-po-override-border",
  "jade":            "bg-po-confidence-high-bg text-po-confidence-high border border-po-confidence-high-border",
  "amber":           "bg-po-suspect-bg text-po-suspect border border-po-suspect-border",
};

export default function Badge({ variant = "neutral", icon: Icon, children, className = "" }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
        "text-[11px] font-medium tabular-nums",
        VARIANTS[variant],
        className,
      ].join(" ")}
    >
      {Icon && <Icon size={12} strokeWidth={2} />}
      {children}
    </span>
  );
}
