// Two-segment toggle (radiogroup). Tokens po-* only; no Radix needed.
// options: [{ value, label }]. Controlled via `value` + `onChange`.
// disabled: when true, all segments are non-interactive + visually muted.
export default function SegmentedToggle({ value, onChange, options, ariaLabel, disabled = false }) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      aria-disabled={disabled || undefined}
      className={[
        "inline-flex rounded-md border border-po-border bg-po-bg p-0.5",
        disabled && "opacity-50 cursor-not-allowed",
      ].filter(Boolean).join(" ")}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        const idx = options.indexOf(opt);
        const onKeyDown = (e) => {
          if (disabled) return;
          if (e.key === "ArrowRight" || e.key === "ArrowDown") {
            e.preventDefault();
            onChange(options[(idx + 1) % options.length].value);
          } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
            e.preventDefault();
            onChange(options[(idx - 1 + options.length) % options.length].value);
          }
        };
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={disabled ? undefined : () => onChange(opt.value)}
            onKeyDown={onKeyDown}
            className={[
              "rounded px-3 py-1 text-sm transition outline-none",
              "focus-visible:ring-1 focus-visible:ring-po-accent",
              "disabled:cursor-not-allowed",
              active
                ? "bg-po-panel text-po-text shadow-sm"
                : "text-po-text-muted hover:text-po-text",
            ].join(" ")}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
