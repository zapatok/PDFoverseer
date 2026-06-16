// Two-segment toggle (radiogroup). Tokens po-* only; no Radix needed.
// options: [{ value, label }]. Controlled via `value` + `onChange`.
export default function SegmentedToggle({ value, onChange, options, ariaLabel }) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex rounded-md border border-po-border bg-po-bg p-0.5"
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={`rounded px-3 py-1 text-sm transition outline-none focus-visible:ring-1 focus-visible:ring-po-accent ${
              active
                ? "bg-po-panel text-po-text shadow-sm"
                : "text-po-text-muted hover:text-po-text"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
