import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "../store/session";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import SaveIndicator from "../ui/SaveIndicator";
import { parseOverrideInput } from "../lib/override-input";

export default function OverridePanel({ hospital, sigla, cell, disabled = false, focusNonce = 0 }) {
  const session = useSessionStore((s) => s.session);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);

  const cellKey = `${hospital}|${sigla}`;
  const saveStatus = pendingSaves[cellKey] ?? "idle";

  const [value, setValue] = useState(cell?.user_override ?? "");
  const [note, setNote] = useState(cell?.override_note ?? "");
  const [focused, setFocused] = useState({ value: false, note: false });
  const [invalid, setInvalid] = useState(false);

  const inputRef = useRef(null);

  // Resync from store when cell changes (e.g., InlineEditCount committed externally),
  // but ONLY if not currently editing that field.
  useEffect(() => {
    if (!focused.value) {
      setValue(cell?.user_override ?? "");
      setInvalid(false); // a fresh cell must not inherit the previous error border
    }
  }, [cell?.user_override, focused.value]);

  useEffect(() => {
    if (!focused.note) setNote(cell?.override_note ?? "");
  }, [cell?.override_note, focused.note]);

  // Focus and select the input when the toggle switches to Manual mode.
  useEffect(() => {
    if (focusNonce > 0 && !disabled && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [focusNonce, disabled]);

  const flushSave = useDebouncedCallback((v, n) => {
    const numericValue = v === "" || v === null ? null : parseInt(v, 10);
    saveOverride(session.session_id, hospital, sigla, numericValue, n || null);
  }, 400);

  const onChangeValue = (e) => {
    const raw = e.target.value;
    setValue(raw);
    const { value: parsed, valid } = parseOverrideInput(raw);
    setInvalid(!valid);
    if (valid) flushSave(parsed === null ? "" : String(parsed), note);
  };
  const onChangeNote = (e) => {
    setNote(e.target.value);
    // Don't persist while the number field holds an invalid value (e.g. "-5"):
    // saving here would smuggle the rejected number past onChangeValue's guard.
    if (!invalid) flushSave(value, e.target.value);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <input
          ref={inputRef}
          type="number"
          min={0}
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
                : "border-po-border bg-po-bg focus:border-po-accent"
          }`}
        />
        <SaveIndicator status={saveStatus} />
      </div>
      <textarea
        value={note}
        placeholder="Nota (opcional)"
        onChange={onChangeNote}
        onFocus={() => setFocused((f) => ({ ...f, note: true }))}
        onBlur={() => setFocused((f) => ({ ...f, note: false }))}
        disabled={disabled}
        rows={3}
        className={`w-full rounded border px-2 py-1.5 text-sm placeholder-po-text-subtle outline-none resize-none ${
          disabled
            ? "cursor-not-allowed border-po-border bg-po-bg text-po-text-muted opacity-50"
            : "border-po-border bg-po-bg focus:border-po-accent"
        }`}
      />
    </div>
  );
}
