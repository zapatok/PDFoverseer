import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "../store/session";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import SaveIndicator from "../ui/SaveIndicator";
import { parseOverrideInput } from "../lib/override-input";

export default function OverridePanel({ hospital, sigla, cell, disabled = false, focusNonce = 0, maxPages = null, countType = null }) {
  const session = useSessionStore((s) => s.session);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);

  const cellKey = `${hospital}|${sigla}`;
  const saveStatus = pendingSaves[cellKey] ?? "idle";

  const [value, setValue] = useState(cell?.user_override ?? "");
  const [focused, setFocused] = useState({ value: false });
  const [invalid, setInvalid] = useState(false);
  // Over-cap confirmation (task 5): holds the pending value while we wait for
  // the operator to confirm "sí, de verdad son N documentos en M páginas".
  const [pendingOverCap, setPendingOverCap] = useState(null);

  const inputRef = useRef(null);

  // Resync from store when cell changes (e.g., InlineEditCount committed externally),
  // but ONLY if not currently editing that field.
  useEffect(() => {
    if (!focused.value) {
      setValue(cell?.user_override ?? "");
      setInvalid(false); // a fresh cell must not inherit the previous error border
      setPendingOverCap(null);
    }
  }, [cell?.user_override, focused.value]);

  // Focus and select the input when the toggle switches to Manual mode.
  useEffect(() => {
    if (focusNonce > 0 && !disabled && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [focusNonce, disabled]);

  const flushSave = useDebouncedCallback((v) => {
    const numericValue = v === "" || v === null ? null : parseInt(v, 10);
    saveOverride(session.session_id, hospital, sigla, numericValue);
  }, 400);

  const onChangeValue = (e) => {
    const raw = e.target.value;
    setValue(raw);
    // Typing again always clears a stale confirmation — the operator must
    // re-trigger it deliberately, not carry over a confirm for an old value.
    setPendingOverCap(null);
    const { value: parsed, valid, overCap } = parseOverrideInput(raw, { maxPages });
    setInvalid(!valid && !overCap);
    if (valid) {
      flushSave(parsed === null ? "" : String(parsed));
    } else if (overCap) {
      setPendingOverCap(parsed);
    }
  };

  // The confirmed save is an explicit click, not a debounced keystroke — it
  // calls saveOverride directly (with the flag) instead of flushSave, which
  // only forwards the plain value. NOTE: manual is intentionally omitted —
  // that flag means "entered via the HLL no-PDF manual-entry flow" (sets
  // cell.manual_entry, see api/state.py::apply_user_override), a different
  // concept from this confirmation; the plain-valid path above (flushSave)
  // never sets it either, so this stays consistent for every hospital.
  const confirmOverCap = () => {
    saveOverride(session.session_id, hospital, sigla, pendingOverCap, {
      allowOverPages: true,
    });
    setPendingOverCap(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <input
          ref={inputRef}
          type="number"
          min={0}
          max={maxPages ?? undefined}
          value={value}
          placeholder={String(cell?.ocr_count ?? cell?.filename_count ?? 0)}
          onChange={onChangeValue}
          onFocus={() => setFocused((f) => ({ ...f, value: true }))}
          onBlur={() => setFocused((f) => ({ ...f, value: false }))}
          disabled={disabled}
          className={`w-24 rounded border px-2 py-1.5 text-sm tabular-nums outline-none ${
            disabled
              ? "cursor-not-allowed border-po-border bg-po-bg text-po-text-muted opacity-50"
              : invalid
                ? "border-po-error bg-po-bg focus:border-po-error"
                : pendingOverCap != null
                  ? "border-po-suspect-border bg-po-bg focus:border-po-suspect-border"
                  : "border-po-border bg-po-bg focus:border-po-accent"
          }`}
        />
        <SaveIndicator status={saveStatus} />
      </div>
      {invalid && maxPages != null && (
        <p className="text-xs text-po-error mt-1">máx. {maxPages} (páginas)</p>
      )}
      {pendingOverCap != null && (
        <div className="mt-1 flex items-center gap-2 text-xs text-po-suspect">
          <span>
            La celda tiene {maxPages} páginas. ¿Confirmas {pendingOverCap} documentos?
          </span>
          <button
            type="button"
            className="rounded border border-po-border px-1.5 py-0.5 text-po-text hover:border-po-border-strong"
            onClick={confirmOverCap}
          >
            Confirmar
          </button>
          <button
            type="button"
            className="text-po-text-muted hover:text-po-text"
            onClick={() => setPendingOverCap(null)}
          >
            Cancelar
          </button>
        </div>
      )}
    </div>
  );
}
