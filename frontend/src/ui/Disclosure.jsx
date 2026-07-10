import { useState } from "react";
import { ChevronRight } from "lucide-react";

/**
 * Disclosure — collapsible section with a keyboard-accessible summary button.
 *
 * A native <button> (not <details>/<summary>) so Enter/Space work everywhere
 * and screen readers get aria-expanded (the ReorgMenu <summary> A11y lesson).
 *
 * @param {object} props
 * @param {import("react").ReactNode} props.summary - header content.
 * @param {boolean} [props.defaultOpen] - start expanded (default false).
 * @param {import("react").ReactNode} props.children
 */
export default function Disclosure({ summary, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 text-left text-xs font-medium uppercase tracking-wider text-po-text-muted hover:text-po-text transition"
      >
        <ChevronRight
          size={13}
          strokeWidth={2}
          className={["transition-transform", open ? "rotate-90" : ""].join(" ")}
          aria-hidden
        />
        <span className="flex-1 min-w-0">{summary}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}
