import { useEffect, useState } from "react";
import { MousePointer2, FileStack, PenLine, Users, ScanSearch, ClipboardCopy, Info, X, Trash2, Ratio } from "lucide-react";
import NotePanel from "./NotePanel";
import ReorganizacionPanel from "./ReorganizacionPanel";
import OverridePanel from "./OverridePanel";
import EmptyState from "../ui/EmptyState";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Tooltip from "../ui/Tooltip";
import PdfCoverViewer from "./PdfCoverViewer";
import { SIGLA_LABELS, siglaDisplay } from "../lib/sigla-labels";
import { SIGLA_DESCRIPTION, SIGLA_PAGE_RANGE, formatPageRange, countTypeFor } from "../lib/sigla-info";
import { METHOD_LABEL } from "../lib/method-labels";
import { composeMethodInfo } from "../lib/method-info";
import { useSessionStore } from "../store/session";
import { cellWorkerCount } from "../lib/worker-count";
import { computeCellCount, computeFilesCount } from "../lib/cellCount";
import SegmentedToggle from "../ui/SegmentedToggle";
import { hasOverride, isCappedCountType, showsWorkerCounter } from "../lib/cell-status";
import { copyFlavorStub } from "../lib/flavorStub";
import { api } from "../lib/api";
import { toast } from "sonner";

function NearMatchRow({ nm, hospital, sigla, sessionId, pdfIndex }) {
  const [viewerOpen, setViewerOpen] = useState(false);
  const clearNearMatches = useSessionStore((s) => s.clearNearMatches);
  // pdfIndex < 0 means the near-match PDF name was not found among the
  // cell's per_file keys (e.g. nested-folder name forms diverge). Opening
  // any URL would silently show the wrong PDF, so the viewer is disabled.
  const located = pdfIndex >= 0;
  const pdfUrl =
    sessionId && located
      ? api.cellPdfUrl(sessionId, hospital, sigla, pdfIndex)
      : null;

  async function handleCopyStub() {
    try {
      await copyFlavorStub(nm);
      toast.success("Stub copiado al portapapeles");
    } catch {
      toast.error("No se pudo copiar al portapapeles");
    }
  }

  return (
    <li className="flex flex-col gap-1 py-2 border-b border-po-border last:border-0">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-xs text-po-text truncate flex-1">{nm.pdf_name}</span>
        <span className="text-xs text-po-text-muted shrink-0">p.&nbsp;{nm.page_index + 1}</span>
        <Badge variant="amber">{nm.flavor_name}</Badge>
      </div>
      <div className="flex items-center gap-1.5 flex-wrap text-xs text-po-text-muted">
        <span>Coincide: {nm.matched_anchors.join(", ")}</span>
        {nm.missing_anchors.length > 0 && (
          <span>· Falta: {nm.missing_anchors.join(", ")}</span>
        )}
      </div>
      <div className="flex items-center gap-2 mt-1">
        <Button
          variant="secondary"
          icon={ScanSearch}
          onClick={() => setViewerOpen(true)}
          disabled={!sessionId || !located}
        >
          Ver portada
        </Button>
        {!located && (
          <span className="text-xs text-po-text-muted">
            PDF no ubicado en la celda
          </span>
        )}
        <Button
          variant="secondary"
          icon={ClipboardCopy}
          onClick={handleCopyStub}
        >
          Marcar como nuevo flavor
        </Button>
        <Button
          variant="ghost"
          icon={X}
          onClick={() =>
            clearNearMatches(sessionId, hospital, sigla, {
              pdf_name: nm.pdf_name,
              page_index: nm.page_index,
            })
          }
        >
          Descartar
        </Button>
      </div>
      {viewerOpen && pdfUrl && (
        <PdfCoverViewer
          open={viewerOpen}
          onClose={() => setViewerOpen(false)}
          url={pdfUrl}
          pageNumber={nm.page_index + 1}
          title={`${nm.pdf_name} — p. ${nm.page_index + 1}`}
        />
      )}
    </li>
  );
}

function NearMatchesSection({ hospital, sigla, cell, sessionId }) {
  const clearNearMatches = useSessionStore((s) => s.clearNearMatches);
  const nearMatches = cell.near_matches;
  if (!nearMatches || nearMatches.length === 0) return null;

  // Derive file indices: sort the per_file keys (bare filenames, alphabetically)
  // to match the server-side sorted(folder.rglob("*.pdf")) order for flat folders.
  const sortedNames = Object.keys(cell.per_file || {}).sort();

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted flex items-center gap-2">
          Casi-matches
          <Badge variant="amber">{nearMatches.length} candidato{nearMatches.length !== 1 ? "s" : ""} a flavor nuevo</Badge>
        </h4>
        <button
          type="button"
          onClick={() => clearNearMatches(sessionId, hospital, sigla)}
          className="inline-flex items-center gap-1 text-xs text-po-text-muted hover:text-po-error transition shrink-0"
        >
          <Trash2 size={13} strokeWidth={1.75} /> Limpiar todo
        </button>
      </div>
      <ul className="divide-y-0">
        {nearMatches.map((nm, i) => {
          const pdfIndex = sortedNames.indexOf(nm.pdf_name);
          return (
            <NearMatchRow
              key={`${nm.pdf_name}-${nm.page_index}-${i}`}
              nm={nm}
              hospital={hospital}
              sigla={sigla}
              sessionId={sessionId}
              pdfIndex={pdfIndex}
            />
          );
        })}
      </ul>
    </div>
  );
}

function WorkerCountModule({ hospital, sigla, cell, countType = "documents_workers" }) {
  const openWorkerCount = useSessionStore((s) => s.openWorkerCount);
  const status = cell.worker_status;
  // F1 fix: prefer the backend-authoritative worker_count (filtered by present
  // files on disk, set on every PATCH response). Fall back to a local sum over
  // all marks only when worker_count is not yet in the store (initial render
  // before the first PATCH in this session).
  const total =
    cell.worker_count != null
      ? cell.worker_count
      : cellWorkerCount(cell, null);
  const started = status === "en_progreso" || status === "terminado";
  const unit = countType === "checks" ? "chequeos" : "trabajadores";
  const sectionLabel = countType === "checks" ? "Conteo de chequeos" : "Conteo de trabajadores";
  const startLabel = countType === "checks" ? "Contar chequeos" : "Contar trabajadores";

  return (
    <div className="mt-6">
      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-2">
        {sectionLabel}
      </h4>
      {started && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-3xl font-semibold tabular-nums">{total.toLocaleString()}</span>
          <span className="text-xs text-po-text-muted">{unit}</span>
          <Badge variant={status === "terminado" ? "jade" : "amber"}>
            {status === "terminado" ? "Terminado" : "En progreso"}
          </Badge>
        </div>
      )}
      <Button
        variant={started ? "secondary" : "primary"}
        icon={Users}
        onClick={() => openWorkerCount(hospital, sigla)}
      >
        {!started && startLabel}
        {status === "en_progreso" && "Continuar conteo"}
        {status === "terminado" && "Revisar"}
      </Button>
    </div>
  );
}

export default function DetailPanel({ hospital, sigla, cell }) {
  const sessionId = useSessionStore((s) => s.session?.session_id);
  const reorgOps = useSessionStore((s) => s.session?.reorg_ops ?? []);
  const deleteReorgOp = useSessionStore((s) => s.deleteReorgOp);
  const exportManifest = useSessionStore((s) => s.exportManifest);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const applyRatioCell = useSessionStore((s) => s.applyRatioCell);
  const filesTick = useSessionStore((s) => s.filesTick[`${hospital}|${sigla}`] ?? 0);
  const [scanInfo, setScanInfo] = useState(null);
  const [totalPages, setTotalPages] = useState(null);
  const [ratioNOpen, setRatioNOpen] = useState(false);
  const [ratioNValue, setRatioNValue] = useState(2);
  // hasOverride(null) is falsy, so a null cell defaults to "files". These hooks
  // MUST stay above the early return below (Rules of Hooks).
  const [mode, setMode] = useState(hasOverride(cell) ? "manual" : "files");
  const [focusNonce, setFocusNonce] = useState(0);

  // rev-2 #5 — what the sigla's OCR looks for, for the method (i) tooltip.
  useEffect(() => {
    if (!sigla) { setScanInfo(null); return; }
    let alive = true;
    api.getScanInfo(sigla).then((s) => { if (alive) setScanInfo(s); }).catch(() => {});
    return () => { alive = false; };
  }, [sigla]);

  // Incr 2 — compute totalPages for the ≤pages cap (lazy, re-fetches on tick).
  useEffect(() => {
    if (!sessionId || !hospital || !sigla) { setTotalPages(null); return; }
    let alive = true;
    api.getCellFiles(sessionId, hospital, sigla)
      .then((files) => {
        if (alive) setTotalPages(files.reduce((sum, f) => sum + (f.page_count ?? 0), 0));
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [sessionId, hospital, sigla, filesTick]);

  // Re-sync mode from provenance when the selected cell changes; also collapse the
  // ratio-N input so it doesn't leak its open state / value across cells.
  useEffect(() => {
    setMode(hasOverride(cell) ? "manual" : "files");
    setRatioNOpen(false);
    setRatioNValue(2);
  }, [hospital, sigla, cell?.user_override]);

  if (!cell || !sigla) {
    return (
      <EmptyState
        icon={MousePointer2}
        title="Selecciona una categoría"
        description="Elige una sigla de la lista para ver el conteo, ajustar manualmente y abrir los archivos."
      />
    );
  }

  const countType = countTypeFor(sigla);
  const isChecks = countType === "checks";

  const isCompilationSuspect = cell.flags?.includes("compilation_suspect");
  const filesCount = computeFilesCount(cell);
  const total = computeCellCount(cell, countType);
  const label = SIGLA_LABELS[sigla];
  const showLabel = label && label.toLowerCase() !== sigla.toLowerCase();

  // Incr 2 — cap predicate: document-counting siglas cap overrides at ≤ totalPages.
  const isCapped = isCappedCountType(scanInfo?.count_type);
  const maxPages = isCapped ? totalPages : null;

  function handleModeChange(next) {
    setMode(next);
    if (next === "files") {
      // Clear the cell override → total = files sum. The note is independent of
      // the override now (Incr 3C N1), so clearing the override leaves it intact.
      saveOverride(sessionId, hospital, sigla, null);
    } else {
      // Manual: focus the field; no write until the operator types.
      setFocusNonce((n) => n + 1);
    }
  }

  return (
    <div className="rounded-xl bg-po-panel border border-po-border p-5">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="font-mono text-sm text-po-text">{siglaDisplay(sigla)}</span>
        {showLabel && (
          <>
            <span className="text-po-text-muted">·</span>
            <span className="text-sm text-po-text">{label}</span>
          </>
        )}
      </div>

      {!isChecks && (
        <>
          <p className="text-5xl font-semibold tabular-nums mt-4">{total.toLocaleString()}</p>
          <p className="text-xs text-po-text-muted mt-0.5">documentos</p>
        </>
      )}

      {!isChecks && (
        <div className="mt-3 flex items-center gap-3">
          <SegmentedToggle
            ariaLabel="Origen del conteo"
            value={mode}
            onChange={handleModeChange}
            options={[
              { value: "files", label: "Por archivos" },
              { value: "manual", label: "Manual" },
            ]}
          />
          <span className="text-xs text-po-text-muted tabular-nums">
            archivos: {filesCount.toLocaleString()}
          </span>
        </div>
      )}

      {/* Incr 2 — block-action cluster: ratio treatments, visible only in "Por archivos" mode and for non-checks siglas */}
      {!isChecks && mode === "files" && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            icon={Ratio}
            onClick={async () => {
              try {
                await applyRatioCell(sessionId, hospital, sigla, 1);
                toast.success("R1 aplicado — cada página cuenta como 1 documento");
              } catch {
                toast.error("No se pudo aplicar R1");
              }
            }}
          >
            Aplicar R1
          </Button>
          {!ratioNOpen ? (
            <Button
              variant="secondary"
              icon={Ratio}
              onClick={() => setRatioNOpen(true)}
            >
              Aplicar ratio N…
            </Button>
          ) : (
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                min={1}
                value={ratioNValue}
                onChange={(e) => {
                  const parsed = parseInt(e.target.value, 10);
                  setRatioNValue(Number.isNaN(parsed) ? 1 : Math.max(1, parsed));
                }}
                className="w-16 rounded border border-po-border bg-po-bg px-2 py-1 text-sm tabular-nums focus:border-po-accent focus:outline-none"
              />
              <Button
                variant="primary"
                onClick={async () => {
                  try {
                    await applyRatioCell(sessionId, hospital, sigla, ratioNValue);
                    setRatioNOpen(false); // collapse only on success (keep N on failure)
                    toast.success(`Ratio ${ratioNValue} aplicado a archivos Pendiente`);
                  } catch {
                    toast.error("No se pudo aplicar el ratio");
                  }
                }}
              >
                Aplicar
              </Button>
              <Button
                variant="ghost"
                icon={X}
                onClick={() => setRatioNOpen(false)}
              >
                Cancelar
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mt-3">
        {isCompilationSuspect && (
          <Tooltip content="Probable compilación (PDF con >5× páginas esperadas)">
            <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
          </Tooltip>
        )}
        {hasOverride(cell) && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
      </div>

      {SIGLA_DESCRIPTION[sigla] && (
        <div className="mt-4 rounded-lg border border-po-border bg-po-panel-hover px-3 py-2">
          <p className="text-sm text-po-text">{SIGLA_DESCRIPTION[sigla]}</p>
          {SIGLA_PAGE_RANGE[sigla] && (
            <p className="text-xs text-po-text-muted mt-1">
              {formatPageRange(SIGLA_PAGE_RANGE[sigla])}
            </p>
          )}
        </div>
      )}

      {!isChecks && (
        <>
          <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Conteo automático</h4>
          <table className="w-full text-sm">
            <tbody>
              {/* Solo el método automático vigente de la cascada (review #4):
                  OCR si ya se escaneó, si no el conteo por nombre. El override
                  manual vive aparte, en "Ajuste manual". */}
              {cell.ocr_count != null ? (
                <tr>
                  <td className="text-po-text-muted py-1">Por OCR</td>
                  <td className="text-right font-mono tabular-nums">{cell.ocr_count}</td>
                </tr>
              ) : (
                <tr>
                  <td className="text-po-text-muted py-1">Por nombre de archivo</td>
                  <td className="text-right font-mono tabular-nums">{cell.filename_count ?? "—"}</td>
                </tr>
              )}
              <tr>
                <td className="text-po-text-muted py-1">Método</td>
                <td className="text-right">
                  <span className="inline-flex items-center justify-end gap-1">
                    <Tooltip content={`Token interno: ${cell.method ?? "—"}`}>
                      <span>{METHOD_LABEL[cell.method] ?? cell.method ?? "—"}</span>
                    </Tooltip>
                    {cell.method && (
                      <Tooltip content={composeMethodInfo(cell.method, scanInfo)}>
                        <span className="inline-flex">
                          <Info size={13} strokeWidth={1.75} className="text-po-text-muted cursor-help" />
                        </span>
                      </Tooltip>
                    )}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>

          <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual</h4>
          <OverridePanel
            hospital={hospital}
            sigla={sigla}
            cell={cell}
            disabled={mode === "files"}
            focusNonce={focusNonce}
            maxPages={maxPages}
            countType={scanInfo?.count_type}
          />
        </>
      )}

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Nota</h4>
      <NotePanel hospital={hospital} sigla={sigla} cell={cell} />

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Reorganización</h4>
      <ReorganizacionPanel
        hospital={hospital}
        sigla={sigla}
        ops={reorgOps}
        onDelete={(opId) => deleteReorgOp(sessionId, opId)}
        onExport={() => exportManifest(sessionId)}
      />

      {/* Worker/checks counting module: documents_workers (charla/chintegral/dif_pts)
          and checks (maquinaria). dif_pts wired to N15 in Incr 3B. Keep above
          near-match suspects. */}
      {showsWorkerCounter(countType) && (
        <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} countType={countType} />
      )}

      <NearMatchesSection
        hospital={hospital}
        sigla={sigla}
        cell={cell}
        sessionId={sessionId}
      />
    </div>
  );
}
