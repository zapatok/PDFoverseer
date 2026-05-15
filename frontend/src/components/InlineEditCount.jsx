// Extracted from CategoryRow.jsx (FASE 4 Task 2.5). Refactor puro: no
// behavior change. Reusado en FileList row para per-file overrides.

import { useState, useEffect, useRef } from "react";

export default function InlineEditCount({ value, onCommit, placeholder = null, autoFocus = false }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const buttonRef = useRef(null);

  // Value-reset effect (Task 15): keep draft in sync when value changes externally.
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  // AutoFocus effect: enter edit mode immediately when autoFocus prop is true.
  // Separate from the value-reset effect — different deps, different concern.
  useEffect(() => {
    if (autoFocus) {
      setDraft(value ?? "");
      setEditing(true);
    }
    // Only run on mount / when autoFocus becomes true — not on value changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFocus]);

  if (!editing) {
    const displayValue = value != null ? value.toLocaleString() : (placeholder ?? "—");
    return (
      <button
        ref={buttonRef}
        onClick={(e) => {
          e.stopPropagation();
          setDraft(value ?? "");
          setEditing(true);
        }}
        className="font-mono tabular-nums text-sm w-14 text-right hover:text-po-accent focus-visible:outline-none focus-visible:text-po-accent"
      >
        {displayValue}
      </button>
    );
  }

  return (
    <input
      type="number"
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          const v = parseInt(draft, 10);
          if (!Number.isNaN(v)) onCommit(v);
          setEditing(false);
        } else if (e.key === "Escape") {
          setEditing(false);
        }
      }}
      onBlur={() => setEditing(false)}
      className="font-mono tabular-nums text-sm w-14 text-right bg-po-bg border border-po-accent rounded px-1 focus-visible:outline-none"
    />
  );
}
