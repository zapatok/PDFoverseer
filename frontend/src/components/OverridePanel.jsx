import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";

export default function OverridePanel({ hospital, sigla, cell }) {
  const { session, saveOverride } = useSessionStore();
  const [value, setValue] = useState(cell?.user_override ?? "");
  const [note, setNote] = useState(cell?.override_note ?? "");

  // Reset local state when the selected cell changes
  useEffect(() => {
    setValue(cell?.user_override ?? "");
    setNote(cell?.override_note ?? "");
  }, [hospital, sigla, cell?.user_override, cell?.override_note]);

  const persist = () => {
    if (!session) return;
    const v = value === "" ? null : Number.parseInt(value, 10);
    if (v !== null && (Number.isNaN(v) || v < 0)) return;
    saveOverride(session.session_id, hospital, sigla, v, note || null);
  };

  return (
    <div className="space-y-2 text-sm">
      <label className="block">
        <span className="text-slate-400">Override:</span>
        <input
          type="number"
          min={0}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={persist}
          className="ml-2 w-24 bg-slate-800 border border-slate-700 rounded px-2 py-1"
        />
      </label>
      <label className="block">
        <span className="text-slate-400">Nota:</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={persist}
          rows={3}
          className="mt-1 w-full bg-slate-800 border border-slate-700 rounded px-2 py-1"
        />
      </label>
    </div>
  );
}
