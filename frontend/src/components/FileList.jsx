import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { FileText, FileStack, FileX, MousePointer2, MoreHorizontal } from "lucide-react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import { toast } from "sonner";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";
import Tooltip from "../ui/Tooltip";
import InlineEditCount from "./InlineEditCount";
import OriginChip from "./OriginChip";
import PresenceBadge from "./PresenceBadge";
import { fileCountDisplay } from "../lib/file-origin";
import { countDiffersFromPages, FILTER_ORIGINS, matchesFilters } from "../lib/file-filters";
import { hasOverride, isCappedCountType, perFileCountEditable } from "../lib/cell-status";
import { SIGLAS } from "../lib/sigla-labels";
import { DEFAULT_ROTATION_DEG, ROTATION_OPTIONS } from "../lib/rotation-options";
import { cellLockHolder } from "../lib/presence";
import { getParticipantId } from "../lib/identity";

// Known hospitals in canonical order.
const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

/**
 * Compact popover menu for creating a whole-file reorg op.
 * Uses <details>/<summary> to avoid needing a portal.
 */
function ReorgMenu({ file, srcHospital, srcSigla, sessionId, onCreated, disabled = false }) {
  const addReorgOp = useSessionStore((s) => s.addReorgOp);
  const detailsRef = useRef(null);

  const [opType, setOpType] = useState("move_file");
  const [destHospital, setDestHospital] = useState(
    HOSPITALS.find((h) => h !== srcHospital) ?? HOSPITALS[0],
  );
  const [destSigla, setDestSigla] = useState(srcSigla);
  const [empresa, setEmpresa] = useState("");
  const [rotDeg, setRotDeg] = useState(DEFAULT_ROTATION_DEG);
  const [busy, setBusy] = useState(false);

  // Close the popover after a successful submit
  function close() {
    if (detailsRef.current) detailsRef.current.open = false;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!sessionId) return;
    setBusy(true);
    try {
      await addReorgOp(sessionId, srcHospital, srcSigla, {
        op_type: opType,
        source: { file: file.name },
        // rotate stays in the same cell — dest == source (a different dest would
        // tell paso-1 to move a file that should only be rotated in place).
        dest:
          opType === "rotate"
            ? { hospital: srcHospital, sigla: srcSigla }
            : { hospital: destHospital, sigla: destSigla },
        empresa: empresa || null,
        preserve_date: true,
        // rotation_deg must be a valid int (Pydantic rejects null for `int = 0`).
        rotation_deg: opType === "rotate" ? rotDeg : 0,
        // Let the backend resolve counts per op_type: move_file → the file's per_file
        // contribution + its worker marks; rotate/split_in_place → 0 (no count change).
        // Hardcoding here would wrongly give a rotate a doc delta and never carry workers.
        doc_count: null,
        worker_count: null,
        note: null,
      });
      toast.success(`Operación creada — ${file.name}`);
      setEmpresa("");
      close();
      onCreated?.();
    } catch {
      // addReorgOp already toasts the error
    } finally {
      setBusy(false);
    }
  }

  return (
    <details ref={detailsRef} className="relative">
      <summary
        aria-disabled={disabled || undefined}
        onClick={disabled ? (e) => e.preventDefault() : undefined}
        onKeyDown={
          disabled
            ? (e) => {
                // <details> toggles on Enter/Space too; onClick only blocks the
                // mouse, so guard the keyboard path or a locked cell's reorg menu
                // would still open for keyboard users.
                if (e.key === "Enter" || e.key === " ") e.preventDefault();
              }
            : undefined
        }
        className={[
          "list-none flex items-center justify-center w-7 h-7 rounded text-po-text-muted",
          disabled
            ? "opacity-50 cursor-not-allowed"
            : "hover:text-po-text hover:bg-po-panel-hover cursor-pointer",
        ].join(" ")}
        title={disabled ? "Bloqueado por otro participante" : "Reorganizar archivo"}
        aria-label="Reorganizar archivo"
      >
        <MoreHorizontal size={14} strokeWidth={1.75} />
      </summary>
      {/* Popover card — positioned absolutely; z-10 clears the file list rows */}
      <form
        onSubmit={handleSubmit}
        className="absolute right-0 z-10 mt-1 w-56 rounded-lg border border-po-border bg-po-panel shadow-lg p-3 space-y-2 text-xs"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-medium text-po-text truncate">{file.name}</p>

        {/* op_type */}
        <div className="space-y-0.5">
          <label className="text-po-text-muted">Tipo</label>
          <select
            value={opType}
            onChange={(e) => setOpType(e.target.value)}
            className="w-full rounded border border-po-border bg-po-bg px-2 py-1 text-xs focus:border-po-accent focus:outline-none"
          >
            <option value="move_file">Mover a otra celda</option>
            <option value="rotate">Rotar</option>
          </select>
        </div>

        {/* destination hospital — always shown */}
        <div className="space-y-0.5">
          <label className="text-po-text-muted">Hospital destino</label>
          <select
            value={destHospital}
            onChange={(e) => setDestHospital(e.target.value)}
            className="w-full rounded border border-po-border bg-po-bg px-2 py-1 text-xs focus:border-po-accent focus:outline-none"
          >
            {HOSPITALS.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>

        {/* destination sigla — shown for move_file */}
        {opType !== "rotate" && (
          <div className="space-y-0.5">
            <label className="text-po-text-muted">Categoría destino</label>
            <select
              value={destSigla}
              onChange={(e) => setDestSigla(e.target.value)}
              className="w-full rounded border border-po-border bg-po-bg px-2 py-1 text-xs focus:border-po-accent focus:outline-none"
            >
              {SIGLAS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        )}

        {/* rotation degrees — shown for rotate */}
        {opType === "rotate" && (
          <div className="space-y-0.5">
            <label className="text-po-text-muted">Grados</label>
            <select
              value={rotDeg}
              onChange={(e) => setRotDeg(Number(e.target.value))}
              className="w-full rounded border border-po-border bg-po-bg px-2 py-1 text-xs focus:border-po-accent focus:outline-none"
            >
              {ROTATION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* optional empresa */}
        <div className="space-y-0.5">
          <label className="text-po-text-muted">Empresa (opcional)</label>
          <input
            type="text"
            value={empresa}
            onChange={(e) => setEmpresa(e.target.value)}
            placeholder="Razón social"
            className="w-full rounded border border-po-border bg-po-bg px-2 py-1 text-xs placeholder-po-text-subtle focus:border-po-accent focus:outline-none"
          />
        </div>

        <div className="flex gap-1.5 pt-1">
          <button
            type="submit"
            disabled={busy}
            className="flex-1 rounded-md bg-po-accent text-white text-xs px-2 py-1 font-medium hover:bg-po-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {busy ? "Guardando…" : "Crear op."}
          </button>
          <button
            type="button"
            onClick={close}
            className="rounded-md border border-po-border text-po-text-muted text-xs px-2 py-1 hover:text-po-text hover:border-po-border-strong transition"
          >
            Cancelar
          </button>
        </div>
      </form>
    </details>
  );
}

export default function FileList({ hospital, sigla }) {
  const session = useSessionStore((s) => s.session);
  const openLightbox = useSessionStore((s) => s.openLightbox);
  const savePerFileOverride = useSessionStore((s) => s.savePerFileOverride);
  const cell = useSessionStore((s) => s.session?.cells?.[hospital]?.[sigla]);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  // M3a: raw presence selector — never `?? []` inside a selector (Zustand v5 footgun).
  const presence = useSessionStore((s) => s.presence);
  // Re-fetch after an OCR scan finishes for this cell (G3, review #5/#6).
  const tick = useSessionStore((s) => s.filesTick[`${hospital}|${sigla}`] ?? 0);
  const [files, setFiles] = useState(null);
  const [search, setSearch] = useState("");
  const [activeOrigins, setActiveOrigins] = useState([]);
  const [scanInfo, setScanInfo] = useState(null);
  // E1: a per-file save (savePerFileOverride, all completion paths — success,
  // 409, generic error) bumps filesTick to force this effect to re-fetch and
  // show server truth. That refetch sets `files` to null first, which swaps
  // the <ul> for the Skeleton view (unmount) and later mounts a BRAND NEW <ul>
  // — a fresh DOM node always starts at scrollTop 0. Without this guard, every
  // single per-file edit silently scrolls a long list back to the top.
  const listRef = useRef(null);
  const savedScrollRef = useRef(null);
  const prevCellKeyRef = useRef(null);

  useEffect(() => {
    if (!session?.session_id || !hospital || !sigla) {
      setFiles(null);
      prevCellKeyRef.current = null;
      return;
    }
    const cellKey = `${hospital}|${sigla}`;
    // Only preserve scroll when this run was triggered by a tick bump on the
    // SAME cell (a per-file save refetch) — not when the operator navigated
    // to a different hospital/sigla, where resetting to the top is correct.
    // Two independent decisions: null the snapshot ONLY on a genuine cell
    // change; refresh it only when the <ul> is actually mounted. When a second
    // tick bump lands mid-refetch (Skeleton shown, listRef.current === null —
    // two quick stepper clicks), neither applies: keep the FIRST bump's
    // snapshot instead of discarding it and snapping the list to the top.
    if (prevCellKeyRef.current !== cellKey) {
      savedScrollRef.current = null;
    } else if (listRef.current) {
      savedScrollRef.current = listRef.current.scrollTop;
    }
    prevCellKeyRef.current = cellKey;
    setFiles(null);
    api.getCellFiles(session.session_id, hospital, sigla)
      .then(setFiles)
      .catch((err) => setFiles({ error: String(err) }));
  }, [session?.session_id, hospital, sigla, tick]);

  // Restore the pre-refetch scroll position once the new <ul> is mounted.
  useLayoutEffect(() => {
    if (savedScrollRef.current != null && listRef.current) {
      listRef.current.scrollTop = savedScrollRef.current;
      savedScrollRef.current = null;
    }
  }, [files]);

  // Fetch sigla scan-info to determine if page-cap applies (Incr 2).
  useEffect(() => {
    if (!sigla) { setScanInfo(null); return; }
    let alive = true;
    api.getScanInfo(sigla).then((s) => { if (alive) setScanInfo(s); }).catch(() => {});
    return () => { alive = false; };
  }, [sigla]);

  // Per-file count is capped at page_count when the sigla counts documents or documents+workers.
  const isCapped = isCappedCountType(scanInfo?.count_type);

  // M3a: read-only gating. Plain calls, not hooks — safe here despite early returns below.
  const lockHolder = cellLockHolder(presence, hospital, sigla, getParticipantId());
  const locked = lockHolder !== null;

  if (!sigla) {
    return (
      <EmptyState
        icon={MousePointer2}
        title="Selecciona una categoría"
        description="Elige una sigla para ver los archivos PDF asociados."
      />
    );
  }

  if (files === null) {
    return (
      <div className="space-y-2">
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10" />)}
      </div>
    );
  }

  if (files?.error) {
    return (
      <EmptyState
        icon={FileX}
        title="No se pudieron cargar los archivos"
        description={files.error}
      />
    );
  }

  if (files.length === 0) {
    return (
      <EmptyState
        icon={FileX}
        title="Sin archivos"
        description="Esta categoría no tiene archivos PDF en este mes."
      />
    );
  }

  // Stable order — files keep the backend's folder/filename order so a row stays
  // put where the operator acts on it (no reordering on edit).
  const filtered = files.filter((f) => matchesFilters(f, search, activeOrigins));

  return (
    <div className="rounded-xl bg-po-panel border border-po-border overflow-hidden">
      {/* M3a lock notice */}
      {locked && (
        <div className="flex items-center gap-2 border-b border-po-suspect-border bg-po-suspect-bg px-3 py-2 text-xs text-po-suspect">
          <PresenceBadge participant={lockHolder} size="sm" />
          <span>{lockHolder.name} está editando esta celda</span>
        </div>
      )}
      {hasOverride(cell) && (
        <div className="flex items-start gap-2 border-b border-po-suspect-border bg-po-suspect-bg px-3 py-2 text-xs text-po-suspect">
          <span aria-hidden>⚠</span>
          <span>
            La celda usa un total manual ({cell.user_override}) que anula los archivos.{" "}
            <button
              type="button"
              disabled={locked}
              onClick={
                locked
                  ? undefined
                  : () => saveOverride(session.session_id, hospital, sigla, null)
              }
              className="underline underline-offset-2 hover:text-po-text disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
            >
              usar conteo por archivos
            </button>
          </span>
        </div>
      )}
      <div className="p-2 border-b border-po-border">
        <input
          placeholder="Buscar archivo…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-transparent text-sm text-po-text placeholder-po-text-subtle focus:outline-none px-2 py-1"
        />
      </div>
      <div
        role="group"
        aria-label="Filtrar por origen"
        className="flex flex-wrap gap-1 border-b border-po-border px-2 py-1.5"
      >
        {FILTER_ORIGINS.map((o) => {
          const active = activeOrigins.includes(o);
          return (
            <button
              key={o}
              type="button"
              aria-pressed={active}
              onClick={() =>
                setActiveOrigins((prev) =>
                  prev.includes(o) ? prev.filter((x) => x !== o) : [...prev, o],
                )
              }
              className={[
                "rounded-full border px-2 py-0.5 text-[11px] transition outline-none",
                "focus-visible:ring-1 focus-visible:ring-po-accent",
                active
                  ? "border-po-accent bg-po-panel-hover text-po-accent"
                  : "border-po-border text-po-text-muted hover:border-po-border-strong",
              ].join(" ")}
            >
              {o}
            </button>
          );
        })}
      </div>
      <ul ref={listRef} className="max-h-[60vh] overflow-y-auto">
        {filtered.map((f, i) => (
          <li
            key={`${f.name}-${i}`}
            className="grid grid-cols-[minmax(0,1fr)_3rem_1.25rem_6.5rem_5.5rem_2rem] items-center gap-2 px-3 py-2 hover:bg-po-panel-hover transition"
          >
            {/* icon + name — the lightbox trigger; name scrolls horizontally */}
            <button
              type="button"
              onClick={() => openLightbox(hospital, sigla, files.indexOf(f))}
              className="flex items-center gap-2 min-w-0 text-left"
              title={f.name}
            >
              <FileText size={14} strokeWidth={1.75} className="text-po-text-muted shrink-0" />
              <span className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs text-po-text">
                {f.name}
              </span>
            </button>
            {/* Npp — own column, non-interactive */}
            <span className="text-xs tabular-nums text-po-text-muted text-right">{f.page_count}pp</span>
            {/* compilation icon — own column (empty when not suspect), non-interactive */}
            {f.suspect ? (
              <Tooltip content="Probable compilación">
                <span className="flex justify-center"><FileStack size={14} strokeWidth={1.75} className="text-po-suspect" /></span>
              </Tooltip>
            ) : (
              <span />
            )}
            {/* count — editable, stops propagation. Pendiente shows "—" (not
                counted yet), Revisar shows its real 0; both stay editable.
                checks (maquinaria) is the exception (U3): its tally comes from
                worker_marks, a per-file override there is persisted-but-ignored,
                so it renders plain text instead of an inert editor. */}
            <div onClick={(e) => e.stopPropagation()}>
              {(() => {
                const { value, placeholder } = fileCountDisplay(f.origin, f.effective_count);
                if (!perFileCountEditable(scanInfo?.count_type)) {
                  return (
                    <span className="font-mono tabular-nums text-sm w-full text-right inline-block text-po-text-muted">
                      {value != null ? value.toLocaleString() : (placeholder ?? "—")}
                    </span>
                  );
                }
                // E3: subtle text-tone cue when this file's effective count
                // differs from its page count (doc-counting cells only) — a
                // hint the "1 doc per file" default may be wrong, not an error.
                const tinted = countDiffersFromPages(f, scanInfo?.count_type);
                // D2: always-visible -/+ steppers — same optimistic update +
                // save call as the typed-value path (InlineEditCount's
                // onCommit below), just without the over-cap confirmation
                // dance: a "+" past the pages cap 422s and the store
                // toasts+reverts, same honest feedback as any other failed save.
                const commitStep = (delta) => {
                  const next = Math.max(0, (value ?? 0) + delta);
                  setFiles((prev) =>
                    prev.map((row) =>
                      row.name === f.name
                        ? { ...row, effective_count: next, override_count: next, origin: "Manual" }
                        : row,
                    ),
                  );
                  savePerFileOverride(session.session_id, hospital, sigla, f.name, next);
                };
                return (
                  <span className="inline-flex items-center gap-0.5">
                    <button
                      type="button"
                      aria-label="Restar un documento"
                      disabled={locked || (value ?? 0) <= 0}
                      onClick={() => commitStep(-1)}
                      className="rounded px-1 text-po-text-muted hover:text-po-text disabled:opacity-30 outline-none focus-visible:ring-1 focus-visible:ring-po-accent"
                    >
                      −
                    </button>
                    <span className={tinted ? "[&_button]:text-po-suspect" : ""}>
                      <InlineEditCount
                        value={value}
                        placeholder={placeholder}
                        disabled={locked}
                        max={isCapped ? (f.page_count ?? null) : null}
                        onCommit={(newCount, opts) => {
                          setFiles((prev) =>
                            prev.map((row) =>
                              row.name === f.name
                                ? { ...row, effective_count: newCount, override_count: newCount, origin: "Manual" }
                                : row,
                            ),
                          );
                          savePerFileOverride(session.session_id, hospital, sigla, f.name, newCount, {
                            allowOverPages: opts?.allowOverPages,
                          });
                        }}
                      />
                    </span>
                    <button
                      type="button"
                      aria-label="Sumar un documento"
                      disabled={locked}
                      onClick={() => commitStep(+1)}
                      className="rounded px-1 text-po-text-muted hover:text-po-text disabled:opacity-30 outline-none focus-visible:ring-1 focus-visible:ring-po-accent"
                    >
                      +
                    </button>
                  </span>
                );
              })()}
            </div>
            {/* origin chip — honest per-file vocabulary (R1/OCR/Manual/Pendiente/Error/Revisar) */}
            <div className="flex justify-start"><OriginChip origin={f.origin ?? "R1"} /></div>
            {/* ⋯ reorganize trigger — whole-file reorg op creator */}
            <div className="flex justify-center" onClick={(e) => e.stopPropagation()}>
              <ReorgMenu
                file={f}
                srcHospital={hospital}
                srcSigla={sigla}
                sessionId={session?.session_id}
                disabled={locked}
                onCreated={() => {}}
              />
            </div>
          </li>
        ))}
      </ul>
      <div className="px-3 py-2 text-xs text-po-text-muted border-t border-po-border">
        {filtered.length} de {files.length}
      </div>
    </div>
  );
}
