import { useEffect, useRef, useState } from "react";
import { FileText, FileStack, FileX, MousePointer2, MoreHorizontal } from "lucide-react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import { toast } from "sonner";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";
import Tooltip from "../ui/Tooltip";
import InlineEditCount from "./InlineEditCount";
import OriginChip from "./OriginChip";
import { fileCountDisplay } from "../lib/file-origin";
import { hasOverride, isCappedCountType } from "../lib/cell-status";
import { SIGLAS } from "../lib/sigla-labels";

// Known hospitals in canonical order.
const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

/**
 * Compact popover menu for creating a whole-file reorg op.
 * Uses <details>/<summary> to avoid needing a portal.
 */
function ReorgMenu({ file, srcHospital, srcSigla, sessionId, onCreated }) {
  const addReorgOp = useSessionStore((s) => s.addReorgOp);
  const detailsRef = useRef(null);

  const [opType, setOpType] = useState("move_file");
  const [destHospital, setDestHospital] = useState(
    HOSPITALS.find((h) => h !== srcHospital) ?? HOSPITALS[0],
  );
  const [destSigla, setDestSigla] = useState(srcSigla);
  const [empresa, setEmpresa] = useState("");
  const [rotDeg, setRotDeg] = useState(90);
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
        dest: { hospital: destHospital, sigla: destSigla },
        empresa: empresa || null,
        preserve_date: true,
        rotation_deg: opType === "rotate" ? rotDeg : null,
        doc_count: file.effective_count ?? 0,
        worker_count: 0,
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
        className="list-none flex items-center justify-center w-7 h-7 rounded text-po-text-muted hover:text-po-text hover:bg-po-panel-hover cursor-pointer"
        title="Reorganizar archivo"
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
              <option value={90}>90°</option>
              <option value={180}>180°</option>
              <option value={270}>270°</option>
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
  // Re-fetch after an OCR scan finishes for this cell (G3, review #5/#6).
  const tick = useSessionStore((s) => s.filesTick[`${hospital}|${sigla}`] ?? 0);
  const [files, setFiles] = useState(null);
  const [search, setSearch] = useState("");
  const [scanInfo, setScanInfo] = useState(null);

  useEffect(() => {
    if (!session?.session_id || !hospital || !sigla) {
      setFiles(null);
      return;
    }
    setFiles(null);
    api.getCellFiles(session.session_id, hospital, sigla)
      .then(setFiles)
      .catch((err) => setFiles({ error: String(err) }));
  }, [session?.session_id, hospital, sigla, tick]);

  // Fetch sigla scan-info to determine if page-cap applies (Incr 2).
  useEffect(() => {
    if (!sigla) { setScanInfo(null); return; }
    let alive = true;
    api.getScanInfo(sigla).then((s) => { if (alive) setScanInfo(s); }).catch(() => {});
    return () => { alive = false; };
  }, [sigla]);

  // Per-file count is capped at page_count when the sigla counts documents or documents+workers.
  const isCapped = isCappedCountType(scanInfo?.count_type);

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
  const filtered = files.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="rounded-xl bg-po-panel border border-po-border overflow-hidden">
      {hasOverride(cell) && (
        <div className="flex items-start gap-2 border-b border-po-suspect-border bg-po-suspect-bg px-3 py-2 text-xs text-po-suspect">
          <span aria-hidden>⚠</span>
          <span>
            La celda usa un total manual ({cell.user_override}) que anula los archivos.{" "}
            <button
              type="button"
              onClick={() =>
                saveOverride(session.session_id, hospital, sigla, null)
              }
              className="underline underline-offset-2 hover:text-po-text"
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
      <ul className="max-h-[60vh] overflow-y-auto">
        {filtered.map((f, i) => (
          <li
            key={`${f.name}-${i}`}
            className="grid grid-cols-[minmax(0,1fr)_3rem_1.25rem_3.5rem_5.5rem_2rem] items-center gap-2 px-3 py-2 hover:bg-po-panel-hover transition"
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
                counted yet), Revisar shows its real 0; both stay editable. */}
            <div onClick={(e) => e.stopPropagation()}>
              {(() => {
                const { value, placeholder } = fileCountDisplay(f.origin, f.effective_count);
                return (
                  <InlineEditCount
                    value={value}
                    placeholder={placeholder}
                    max={isCapped ? (f.page_count ?? null) : null}
                    onCommit={(newCount) => {
                      setFiles((prev) =>
                        prev.map((row) =>
                          row.name === f.name
                            ? { ...row, effective_count: newCount, override_count: newCount, origin: "Manual" }
                            : row,
                        ),
                      );
                      savePerFileOverride(session.session_id, hospital, sigla, f.name, newCount);
                    }}
                  />
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
