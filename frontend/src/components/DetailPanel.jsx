import { useEffect, useState } from "react";
import { MousePointer2, FileStack, PenLine, Users, ScanSearch, ClipboardCopy, Info, X, Trash2 } from "lucide-react";
import OverridePanel from "./OverridePanel";
import EmptyState from "../ui/EmptyState";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Tooltip from "../ui/Tooltip";
import PdfCoverViewer from "./PdfCoverViewer";
import { SIGLA_LABELS, siglaDisplay } from "../lib/sigla-labels";
import { SIGLA_DESCRIPTION, SIGLA_PAGE_RANGE, formatPageRange } from "../lib/sigla-info";
import { METHOD_LABEL } from "../lib/method-labels";
import { composeMethodInfo } from "../lib/method-info";
import { useSessionStore } from "../store/session";
import { computeWorkerCount } from "../lib/worker-count";
import { computeCellCount, computeFilesCount } from "../lib/cellCount";
import SegmentedToggle from "../ui/SegmentedToggle";
import { hasOverride } from "../lib/cell-status";
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

function WorkerCountModule({ hospital, sigla, cell }) {
  const openWorkerCount = useSessionStore((s) => s.openWorkerCount);
  const status = cell.worker_status;
  const total = computeWorkerCount(cell.worker_marks, Object.keys(cell.per_file || {}));
  const started = status === "en_progreso" || status === "terminado";

  return (
    <div className="mt-6">
      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-2">
        Conteo de trabajadores
      </h4>
      {started && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-3xl font-semibold tabular-nums">{total.toLocaleString()}</span>
          <span className="text-xs text-po-text-muted">trabajadores</span>
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
        {!started && "Contar trabajadores"}
        {status === "en_progreso" && "Continuar conteo"}
        {status === "terminado" && "Revisar"}
      </Button>
    </div>
  );
}

export default function DetailPanel({ hospital, sigla, cell }) {
  const sessionId = useSessionStore((s) => s.session?.session_id);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const [scanInfo, setScanInfo] = useState(null);

  // rev-2 #5 — what the sigla's OCR looks for, for the method (i) tooltip.
  useEffect(() => {
    if (!sigla) { setScanInfo(null); return; }
    let alive = true;
    api.getScanInfo(sigla).then((s) => { if (alive) setScanInfo(s); }).catch(() => {});
    return () => { alive = false; };
  }, [sigla]);

  if (!cell || !sigla) {
    return (
      <EmptyState
        icon={MousePointer2}
        title="Selecciona una categoría"
        description="Elige una sigla de la lista para ver el conteo, ajustar manualmente y abrir los archivos."
      />
    );
  }

  const isCompilationSuspect = cell.flags?.includes("compilation_suspect");
  const filesCount = computeFilesCount(cell);
  const total = computeCellCount(cell);
  const label = SIGLA_LABELS[sigla];
  const showLabel = label && label.toLowerCase() !== sigla.toLowerCase();

  const [mode, setMode] = useState(hasOverride(cell) ? "manual" : "files");
  const [focusNonce, setFocusNonce] = useState(0);

  // Re-sync mode from provenance when the selected cell changes.
  useEffect(() => {
    setMode(hasOverride(cell) ? "manual" : "files");
  }, [hospital, sigla, cell?.user_override]);

  function handleModeChange(next) {
    setMode(next);
    if (next === "files") {
      // Clear the cell override → total = files sum.
      saveOverride(sessionId, hospital, sigla, null, cell?.override_note ?? null);
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

      <p className="text-5xl font-semibold tabular-nums mt-4">{total.toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos</p>

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
      />

      {/* Worker counting is a primary action for charla/chintegral — keep it
          above the near-match suspects so a long suspects list never buries it. */}
      {(sigla === "charla" || sigla === "chintegral") && (
        <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} />
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
