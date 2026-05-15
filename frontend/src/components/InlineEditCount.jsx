// Extracted from CategoryRow.jsx (FASE 4 Task 2.5). Refactor puro: no
// behavior change. Reusado en FileList row para per-file overrides.

import { useState, useEffect } from "react";

export default function InlineEditCount({ value, onCommit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  if (!editing) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation();
          setDraft(value ?? "");
          setEditing(true);
        }}
        className="font-mono tabular-nums text-sm w-14 text-right hover:text-po-accent focus-visible:outline-none focus-visible:text-po-accent"
      >
        {value?.toLocaleString() ?? "—"}
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
