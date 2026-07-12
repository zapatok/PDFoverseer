import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import SaveIndicator from "../ui/SaveIndicator";

// N1 (Incr 3C): per-cell note with state, decoupled from the override. A
// por_resolver note forces the cell dot amber (see isCellReady) without
// blocking actions; resuelto is read-only until reopened. Blank clears it.
// locked (M3a): when another participant holds the cell, textarea + buttons
// are disabled so local edits cannot collide with the remote editor.
export default function NotePanel({ hospital, sigla, cell, locked = false }) {
  // A6: per-field selector — only session_id is used here.
  const sessionId = useSessionStore((s) => s.session?.session_id);
  const saveNote = useSessionStore((s) => s.saveNote);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);

  const status = cell?.note_status ?? null;
  const saveStatus = pendingSaves[`${hospital}|${sigla}|note`] ?? "idle";

  const [text, setText] = useState(cell?.note ?? "");
  const [focused, setFocused] = useState(false);
  // §A9: bridges the gap between a keystroke and the debounced save actually
  // starting — saveStatus only becomes "saving" once the 400 ms timer fires,
  // so a resync gated on saveStatus alone still reverts an IMMEDIATE blur to
  // the stale store value for that whole window. Set true on every keystroke,
  // cleared once saveStatus itself picks up "saving" (below) — from then on
  // the store's own bookkeeping (reused, not duplicated) covers the rest.
  const [dirty, setDirty] = useState(false);
  const hasPendingSave = dirty || saveStatus === "saving";

  // Resync from store when note changes externally, but only if not editing
  // AND no local edit is still in flight (§A9 — see hasPendingSave above).
  useEffect(() => {
    if (!focused && !hasPendingSave) setText(cell?.note ?? "");
  }, [cell?.note, focused, hasPendingSave]);

  // Once the debounced save (or an explicit markResolved/reopen) actually
  // starts, saveStatus takes over tracking "in flight" — drop the local
  // `dirty` bridge so it doesn't stick past this save.
  useEffect(() => {
    if (saveStatus === "saving") setDirty(false);
  }, [saveStatus]);

  // The cell identity travels as ARGS, not via the closure: the debounce hook
  // invokes the LATEST render's callback when the timer fires, so a closure
  // read of hospital/sigla would land a note typed on cell X into cell Y if
  // the operator switches selection within the 400 ms window (NotePanel is
  // not keyed by cell). Args are captured at schedule time — the note always
  // saves to the cell where it was typed. Same fix as OverridePanel's
  // flushSave; markResolved/reopen are safe (they cancel + save synchronously).
  const flush = useDebouncedCallback((hosp, sig, value, nextStatus) => {
    saveNote(sessionId, hosp, sig, { text: value, status: nextStatus });
  }, 400);

  const readOnly = status === "resuelto";

  const onChange = (e) => {
    const v = e.target.value;
    setText(v);
    setDirty(true);
    flush(hospital, sigla, v, "por_resolver");
  };

  // Explicit status changes are authoritative: cancel any pending debounced
  // text-save first, or it would fire ~400 ms later and revert the status.
  const markResolved = () => {
    flush.cancel();
    saveNote(sessionId, hospital, sigla, { text, status: "resuelto" });
  };

  const reopen = () => {
    flush.cancel();
    saveNote(sessionId, hospital, sigla, { text, status: "por_resolver" });
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
        disabled={readOnly || locked}
        rows={3}
        className={`w-full rounded border px-2 py-1.5 text-sm placeholder-po-text-subtle outline-none resize-none ${
          readOnly || locked
            ? "cursor-not-allowed border-po-border bg-po-bg text-po-text-muted"
            : "border-po-border bg-po-bg focus:border-po-accent"
        }`}
      />
      {status === "por_resolver" && (
        <Button variant="secondary" onClick={markResolved} disabled={text.trim() === "" || locked}>
          Marcar resuelta
        </Button>
      )}
      {status === "resuelto" && (
        <Button variant="ghost" onClick={reopen} disabled={locked}>
          Reabrir
        </Button>
      )}
    </div>
  );
}
