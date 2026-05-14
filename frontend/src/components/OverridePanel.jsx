import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import SaveIndicator from "../ui/SaveIndicator";

export default function OverridePanel({ hospital, sigla, cell }) {
  const session = useSessionStore((s) => s.session);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);

  const cellKey = `${hospital}|${sigla}`;
  const saveStatus = pendingSaves[cellKey] ?? "idle";

  const [value, setValue] = useState(cell?.user_override ?? "");
  const [note, setNote] = useState(cell?.override_note ?? "");
  const [focused, setFocused] = useState({ value: false, note: false });

  // Resync from store when cell changes (e.g., InlineEditCount committed externally),
  // but ONLY if not currently editing that field.
  useEffect(() => {
    if (!focused.value) setValue(cell?.user_override ?? "");
  }, [cell?.user_override, focused.value]);

  useEffect(() => {
    if (!focused.note) setNote(cell?.override_note ?? "");
  }, [cell?.override_note, focused.note]);

  const flushSave = useDebouncedCallback((v, n) => {
    const numericValue = v === "" || v === null ? null : parseInt(v, 10);
    saveOverride(session.session_id, hospital, sigla, numericValue, n || null);
  }, 400);

  const onChangeValue = (e) => {
    setValue(e.target.value);
    flushSave(e.target.value, note);
  };
  const onChangeNote = (e) => {
    setNote(e.target.value);
    flushSave(value, e.target.value);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <input
          type="number"
          value={value}
          placeholder={String(cell?.ocr_count ?? cell?.filename_count ?? 0)}
          onChange={onChangeValue}
          onFocus={() => setFocused((f) => ({ ...f, value: true }))}
          onBlur={() => setFocused((f) => ({ ...f, value: false }))}
          className="w-24 bg-po-bg border border-po-border rounded px-2 py-1.5 text-sm tabular-nums focus:border-po-accent outline-none"
        />
        <SaveIndicator status={saveStatus} />
      </div>
      <textarea
        value={note}
        placeholder="Nota (opcional)"
        onChange={onChangeNote}
        onFocus={() => setFocused((f) => ({ ...f, note: true }))}
        onBlur={() => setFocused((f) => ({ ...f, note: false }))}
        rows={3}
        className="w-full bg-po-bg border border-po-border rounded px-2 py-1.5 text-sm placeholder-po-text-subtle focus:border-po-accent outline-none resize-none"
      />
    </div>
  );
}
