// Extracted from CategoryRow.jsx (FASE 4 Task 2.5). Refactor puro: no
// behavior change. Reusado en FileList row para per-file overrides.

import { useState, useEffect, useRef } from "react";

// Box geometry per consumer. "default" right-aligns the digits inside a fixed
// box so the counts line up down CategoryRow's column. "stepper" (FileList)
// centers them inside a narrower box, so the flanking −/+ buttons sit at the
// same distance from the digit and the three read as one control.
const BOX_CLASS = {
  default: "w-14 text-right",
  stepper: "w-10 text-center",
};
// Chromium reserves room for the native number spinner on the input's right
// edge, which would shove the stepper's centered digit off-center — and next to
// −/+ the arrows are duplicate UI anyway.
const NO_SPINNER =
  "[&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none";

export default function InlineEditCount({ value, onCommit, placeholder = null, autoFocus = false, max = null, disabled = false, variant = "default" }) {
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
          "font-mono tabular-nums text-sm",
          BOX_CLASS[variant],
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
        onFocus={(e) => e.target.select()}
        min={0}
        max={max ?? undefined}
        title={invalid && max != null ? `máx. ${max} (páginas)` : undefined}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            // Keyboard path: a second Enter while the question is showing =
            // confirm. Without this, confirm is mouse-only (Tab-away discards,
            // and re-parsing the unchanged draft would just re-ask).
            if (overCap != null) {
              onCommit(overCap, { allowOverPages: true });
              setOverCap(null);
              setEditing(false);
              return;
            }
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
        // §A4: blur commits a valid, changed draft — the same path as Enter —
        // instead of silently discarding it. This matches OverridePanel,
        // which autosaves on every keystroke; before this fix, the identical
        // number behaved differently depending on WHERE it was edited.
        // A pending over-cap confirmation still discards unconditionally on
        // blur-to-elsewhere — else the editor + row would sit stuck open
        // (worst in CategoryRow's long-lived rows) until someone came back to
        // Escape it. Clicking Sí/No never blurs: their onMouseDown
        // preventDefault keeps focus on the input, so this handler never
        // races the buttons.
        onBlur={() => {
          if (overCap == null) {
            const v = parseInt(draft, 10);
            const validNumber = !Number.isNaN(v) && v >= 0 && (max === null || v <= max);
            if (validNumber && v !== value) onCommit(v);
          }
          setEditing(false);
          setOverCap(null);
        }}
        className={[
          "font-mono tabular-nums text-sm text-po-text bg-po-bg border rounded px-1 focus-visible:outline-none",
          BOX_CLASS[variant],
          variant === "stepper" ? NO_SPINNER : "",
          invalid ? "border-po-error" : overCap != null ? "border-po-suspect-border" : "border-po-accent",
        ].filter(Boolean).join(" ")}
      />
      {overCap != null && (
        <span className="ml-1 inline-flex items-center gap-1 text-[11px] text-po-suspect whitespace-nowrap">
          ¿{overCap} docs en {max} págs?
          <button
            type="button"
            // Keep focus on the input: without this, mousedown blurs it and the
            // onBlur close would unmount this button before the click lands.
            onMouseDown={(e) => e.preventDefault()}
            onClick={(e) => {
              e.stopPropagation();
              onCommit(overCap, { allowOverPages: true });
              setOverCap(null);
              setEditing(false);
            }}
            className="underline font-medium"
          >
            Sí
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
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
