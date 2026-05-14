import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import Dialog from "../ui/Dialog";
import OverridePanel from "./OverridePanel";
import Badge from "../ui/Badge";
import Tooltip from "../ui/Tooltip";
import { FileStack, PenLine } from "lucide-react";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import { METHOD_LABEL, CONFIDENCE_LABEL } from "../lib/method-labels";

function effectiveCount(cell) {
  return cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
}

function confidenceVariant(cell) {
  if (cell?.confidence === "high") return "confidence-high";
  if (cell?.confidence === "low") return "confidence-low";
  return "neutral";
}

function CountSummary({ cell }) {
  const isCompilationSuspect = cell?.flags?.includes("compilation_suspect");
  const hasOverride = cell?.user_override !== null && cell?.user_override !== undefined;
  return (
    <div>
      <p className="text-4xl font-semibold tabular-nums">{effectiveCount(cell).toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos</p>
      <div className="flex flex-wrap gap-2 mt-3">
        {isCompilationSuspect && (
          <Tooltip content="Probable compilación">
            <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
          </Tooltip>
        )}
        {cell?.confidence && (
          <Badge variant={confidenceVariant(cell)}>{CONFIDENCE_LABEL[cell.confidence] ?? cell.confidence}</Badge>
        )}
        {hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
      </div>
      <table className="w-full text-sm mt-4">
        <tbody>
          <tr><td className="text-po-text-muted py-1 text-xs">Por nombre</td><td className="text-right font-mono tabular-nums text-xs">{cell?.filename_count ?? "—"}</td></tr>
          <tr><td className="text-po-text-muted py-1 text-xs">Por OCR</td><td className="text-right font-mono tabular-nums text-xs">{cell?.ocr_count ?? "—"}</td></tr>
          <tr><td className="text-po-text-muted py-1 text-xs">Método</td><td className="text-right text-xs">{METHOD_LABEL[cell?.method] ?? cell?.method ?? "—"}</td></tr>
        </tbody>
      </table>
    </div>
  );
}

export default function PDFLightbox() {
  const lightbox = useSessionStore((s) => s.lightbox);
  const closeLightbox = useSessionStore((s) => s.closeLightbox);
  const session = useSessionStore((s) => s.session);
  const [files, setFiles] = useState(null);

  useEffect(() => {
    if (!lightbox) { setFiles(null); return; }
    api.getCellFiles(session.session_id, lightbox.hospital, lightbox.sigla)
      .then(setFiles)
      .catch(() => setFiles([]));
  }, [lightbox?.hospital, lightbox?.sigla, session?.session_id]);

  if (!lightbox || !session) return null;

  const cell = session.cells?.[lightbox.hospital]?.[lightbox.sigla] ?? null;
  const filename = files?.[lightbox.fileIndex]?.name ?? "…";
  const pageCount = files?.[lightbox.fileIndex]?.page_count;
  const pdfUrl = api.cellPdfUrl(session.session_id, lightbox.hospital, lightbox.sigla, lightbox.fileIndex);
  const label = SIGLA_LABELS[lightbox.sigla];
  const showLabel = label && label.toLowerCase() !== lightbox.sigla.toLowerCase();

  return (
    <Dialog open={!!lightbox} onOpenChange={(o) => !o && closeLightbox()}>
      <Dialog.Header>
        <div className="flex items-center gap-2 text-sm">
          <span className="font-mono text-po-text-muted">{lightbox.hospital}</span>
          <span className="text-po-text-muted">·</span>
          <span className="font-mono text-po-text">{lightbox.sigla}</span>
          {showLabel && (
            <>
              <span className="text-po-text-muted">·</span>
              <span className="text-po-text">{label}</span>
            </>
          )}
        </div>
        <div className="font-mono text-xs text-po-text-muted truncate mt-0.5">
          {filename}{pageCount ? ` · ${pageCount}pp` : ""}
        </div>
      </Dialog.Header>
      <Dialog.Body>
        <div className="flex-1 bg-black">
          <iframe src={pdfUrl} className="w-full h-full border-0" title={filename} />
        </div>
        <aside className="w-80 border-l border-po-border p-4 overflow-y-auto">
          <CountSummary cell={cell} />
          <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual</h4>
          <OverridePanel hospital={lightbox.hospital} sigla={lightbox.sigla} cell={cell} />
        </aside>
      </Dialog.Body>
    </Dialog>
  );
}
