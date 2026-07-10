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
  // but ONLY if not currently editing that field. A blur-to-elsewhere also
  // DISCARDS a pending over-cap confirmation — the operator walked away from
  // the question. This cannot race the Confirmar/Cancelar clicks: their
  // onMouseDown preventDefault keeps focus on the input, so clicking them
  // never flips focused.value. And while the operator IS focused mid-decision,
  // the !focused.value guard keeps a remote cell update from wiping their
  // pending state.
  useEffect(() => {
    if (!focused.value) {
      setValue(cell?.user_override ?? "");
      setInvalid(false); // a fresh cell must not inherit the previous error border
      setPendingOverCap(null);
    }
  }, [cell?.user_override, focused.value]);

  // Identity change: this instance is NOT keyed by cell (DetailPanel reuses it
  // across sigla/hospital switches), so a pending confirmation must die with
  // the cell it was typed for — otherwise Confirmar would save the old cell's
  // value into the NEWLY selected cell with the cap lifted. Same on a flip to
  // disabled (lock / "Por archivos"): drop the stale prompt, resync the draft.
  useEffect(() => {
    setPendingOverCap(null);
    setValue(cell?.user_override ?? "");
    setInvalid(false);
    // Deliberately NOT depending on cell — the sibling effect above owns
    // steady-state resync; this one only fires on identity/disabled changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hospital, sigla, disabled]);

  // Focus and select the input when the toggle switches to Manual mode.
  useEffect(() => {
    if (focusNonce > 0 && !disabled && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [focusNonce, disabled]);

  // The cell identity travels as ARGS, not via the closure: the debounce hook
  // invokes the LATEST render's callback when the timer fires, so a closure
  // read of hospital/sigla would misdirect a save scheduled on cell X into
  // cell Y if the operator switches selection within the 400 ms window. Args
  // are captured at schedule time — the save always lands on the cell where
  // the value was typed.
  const flushSave = useDebouncedCallback((h, s, v) => {
    const numericValue = v === "" || v === null ? null : parseInt(v, 10);
    saveOverride(session.session_id, h, s, numericValue);
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
      flushSave(hospital, sigla, parsed === null ? "" : String(parsed));
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

  // Cancelar means "keep the previous value", not "keep the refused text" —
  // and since neither the button click (preventDefault) nor Escape blurs the
  // input, the resync effect can't do the revert; do it explicitly here.
  const cancelOverCap = () => {
    setPendingOverCap(null);
    setValue(cell?.user_override ?? "");
    setInvalid(false);
  };

  // Keyboard path while the question is pending: Enter = Confirmar, Escape =
  // Cancelar. Without this, confirm is mouse-only (a Tab-away blur discards).
  // Escape is otherwise unused here — the only global Escape handler is the
  // HistoryDrawer overlay, which can't hold focus in this input while open.
  const onKeyDownValue = (e) => {
    if (pendingOverCap == null) return;
    if (e.key === "Enter") {
      confirmOverCap();
    } else if (e.key === "Escape") {
      cancelOverCap();
    }
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
          onKeyDown={onKeyDownValue}
          onFocus={(e) => { setFocused((f) => ({ ...f, value: true })); e.target.select(); }}
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
      {pendingOverCap != null && !disabled && (
        <div className="mt-1 flex items-center gap-2 text-xs text-po-suspect">
          <span>
            La celda tiene {maxPages} páginas. ¿Confirmas {pendingOverCap} documentos?
          </span>
          <button
            type="button"
            // Keep focus on the input: without this, mousedown blurs it and the
            // resync effect would unmount this button before the click lands.
            onMouseDown={(e) => e.preventDefault()}
            className="rounded border border-po-border px-1.5 py-0.5 text-po-text hover:border-po-border-strong"
            onClick={confirmOverCap}
          >
            Confirmar
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            className="text-po-text-muted hover:text-po-text"
            onClick={cancelOverCap}
          >
            Cancelar
          </button>
        </div>
      )}
    </div>
  );
}
