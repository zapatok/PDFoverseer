import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import SaveIndicator from "../ui/SaveIndicator";

// N1 (Incr 3C): per-cell note with state, decoupled from the override. A
// por_resolver note forces the cell dot amber (see isCellReady) without
// blocking actions; resuelto is read-only until reopened. Blank clears it.
export default function NotePanel({ hospital, sigla, cell }) {
  const session = useSessionStore((s) => s.session);
  const saveNote = useSessionStore((s) => s.saveNote);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);

  const status = cell?.note_status ?? null;
  const saveStatus = pendingSaves[`${hospital}|${sigla}|note`] ?? "idle";

  const [text, setText] = useState(cell?.note ?? "");
  const [focused, setFocused] = useState(false);

  // Resync from store when note changes externally, but only if not editing.
  useEffect(() => {
    if (!focused) setText(cell?.note ?? "");
  }, [cell?.note, focused]);

  const flush = useDebouncedCallback((value, nextStatus) => {
    saveNote(session.session_id, hospital, sigla, { text: value, status: nextStatus });
  }, 400);

  const readOnly = status === "resuelto";

  const onChange = (e) => {
    const v = e.target.value;
    setText(v);
    flush(v, "por_resolver");
  };

  // Explicit status changes are authoritative: cancel any pending debounced
  // text-save first, or it would fire ~400 ms later and revert the status.
  const markResolved = () => {
    flush.cancel();
    saveNote(session.session_id, hospital, sigla, { text, status: "resuelto" });
  };

  const reopen = () => {
    flush.cancel();
    saveNote(session.session_id, hospital, sigla, { text, status: "por_resolver" });
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {status === "por_resolver" && <Badge variant="amber">Por resolver</Badge>}
        {status === "resuelto" && <Badge variant="jade">Resuelta</Badge>}
        <SaveIndicator status={saveStatus} />
      </div>
      <textarea
        value={text}
        placeholder="Anota algo por resolver en esta celda (opcional)"
        onChange={onChange}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        disabled={readOnly}
        rows={3}
        className={`w-full rounded border px-2 py-1.5 text-sm placeholder-po-text-subtle outline-none resize-none ${
          readOnly
            ? "cursor-not-allowed border-po-border bg-po-bg text-po-text-muted"
            : "border-po-border bg-po-bg focus:border-po-accent"
        }`}
      />
      {status === "por_resolver" && (
        <Button variant="secondary" onClick={markResolved} disabled={text.trim() === ""}>
          Marcar resuelta
        </Button>
      )}
      {status === "resuelto" && (
        <Button variant="ghost" onClick={reopen}>
          Reabrir
        </Button>
      )}
    </div>
  );
}
