// Extracted from CategoryRow.jsx (FASE 4 Task 2.5). Refactor puro: no
// behavior change. Reusado en FileList row para per-file overrides.

import { useState, useEffect, useRef } from "react";

export default function InlineEditCount({ value, onCommit, placeholder = null, autoFocus = false, max = null, disabled = false }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [invalid, setInvalid] = useState(false);
  // Over-cap confirmation (task 5): holds the pending value while we wait for
  // the operator to confirm "sí, de verdad son N documentos en M páginas".
  const [overCap, setOverCap] = useState(null);
  const buttonRef = useRef(null);

  // Value-reset effect (Task 15): keep draft in sync when value changes externally.
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  // AutoFocus effect: enter edit mode immediately when autoFocus prop is true.
  // Separate from the value-reset effect — different deps, different concern.
  // Guard with !disabled so a locked cell never auto-opens for editing.
  useEffect(() => {
    if (autoFocus && !disabled) {
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
        disabled={disabled}
        onClick={disabled ? undefined : (e) => {
          e.stopPropagation();
          setDraft(value ?? "");
          setInvalid(false);
          setOverCap(null);
          setEditing(true);
        }}
        className={[
          "font-mono tabular-nums text-sm w-14 text-right",
          disabled
            ? "text-po-text-muted cursor-not-allowed opacity-50"
            : "text-po-text hover:text-po-accent focus-visible:outline-none focus-visible:text-po-accent",
        ].join(" ")}
      >
        {displayValue}
      </button>
    );
  }

  return (
    <>
      <input
        type="number"
        autoFocus
        value={draft}
        onChange={(e) => { setDraft(e.target.value); setInvalid(false); setOverCap(null); }}
        onClick={(e) => e.stopPropagation()}
        min={0}
        max={max ?? undefined}
        title={invalid && max != null ? `máx. ${max} (páginas)` : undefined}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const v = parseInt(draft, 10);
            if (!Number.isNaN(v) && v >= 0 && (max === null || v <= max)) {
              onCommit(v);
              setEditing(false);
            } else if (!Number.isNaN(v) && v >= 0 && max !== null && v > max) {
              // Over-cap is not garbage: the value parses, it just exceeds the
              // pages. Surface a confirmation instead of a mute refusal.
              setOverCap(v);
            } else {
              // not a number / negative → keep editing so the rejected value
              // stays visible with an error cue, instead of silently snapping back.
              setInvalid(true);
            }
          } else if (e.key === "Escape") {
            setEditing(false);
            setOverCap(null);
          }
        }}
        onBlur={() => { if (overCap == null) setEditing(false); }}
        className={`font-mono tabular-nums text-sm w-14 text-right text-po-text bg-po-bg border rounded px-1 focus-visible:outline-none ${
          invalid ? "border-po-error" : overCap != null ? "border-po-suspect-border" : "border-po-accent"
        }`}
      />
      {overCap != null && (
        <span className="ml-1 inline-flex items-center gap-1 text-[11px] text-po-suspect whitespace-nowrap">
          ¿{overCap} docs en {max} págs?
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onCommit(overCap, { allowOverPages: true });
              setOverCap(null);
              setEditing(false);
            }}
            className="underline"
          >
            Sí
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setOverCap(null);
              setEditing(false);
            }}
            className="underline text-po-text-muted"
          >
            No
          </button>
        </span>
      )}
    </>
  );
}
