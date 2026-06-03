import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import Dialog from "../ui/Dialog";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Tooltip from "../ui/Tooltip";
import { FileStack, ScanSearch, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import { wheelToPageStep } from "../lib/viewer-nav";
import OriginChip from "./OriginChip";
import InlineEditCount from "./InlineEditCount";

import { usePdfDocument } from "../hooks/usePdfDocument";
import { useFitScale } from "../hooks/useFitScale";
import { PdfPage } from "./PdfPage";
import { WorkerThumbnails } from "./WorkerThumbnails";
import { WorkerCountViewer } from "./WorkerCountViewer";

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.2;

function FileSummary({ file }) {
  if (!file) {
    return <p className="text-sm text-po-text-muted">Cargando archivo…</p>;
  }
  return (
    <div>
      <p className="text-4xl font-semibold tabular-nums text-po-text">
        {(file.effective_count ?? 1).toLocaleString()}
      </p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos en este archivo</p>
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <OriginChip origin={file.origin ?? "R1"} />
        <Badge variant="neutral">{file.page_count ?? "?"}pp</Badge>
        {file.suspect && (
          <Tooltip content="Probable compilación">
            <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

// Paged inspect viewer on the proven WorkerCountViewer pattern: a thumbnails
// column, fit-to-window by default, one page at a time. Nav (review #9, Daniel's
// choice): scroll = page, Shift+scroll = zoom; +/- and PgUp/Dn also work.
function InspectView({ url, pageCount }) {
  const { doc, error, loading } = usePdfDocument(url);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const wheelAcc = useRef(0);

  const safePageCount = Math.max(pageCount || 0, 1);
  const clampPage = (p) => Math.min(Math.max(p, 1), safePageCount);

  // Reset to page 1 when the file changes; zoom is per-page (resets on page).
  useEffect(() => { setPage(1); }, [url]);
  useEffect(() => { setZoom(1); }, [page]);

  const { panelRef, fitScale } = useFitScale(doc, page);
  const effectiveScale = Math.max(0.1, fitScale * zoom);

  const zoomIn = () => setZoom((z) => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2)));

  const onWheel = (e) => {
    if (e.shiftKey) {
      e.preventDefault();
      if (e.deltaY < 0) zoomIn();
      else zoomOut();
      return;
    }
    const { step, acc } = wheelToPageStep(e.deltaY, wheelAcc.current);
    wheelAcc.current = acc;
    if (step !== 0) {
      e.preventDefault();
      setPage((p) => clampPage(p + step));
    }
  };

  // Keyboard nav while the viewer is alive. Ignore when focus is in the
  // manual-adjust input so digits / "-" don't move the page.
  useEffect(() => {
    const onKey = (e) => {
      const el = document.activeElement;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || el?.isContentEditable) return;
      if (e.key === "PageDown" || e.key === "ArrowDown") { e.preventDefault(); setPage((p) => clampPage(p + 1)); }
      else if (e.key === "PageUp" || e.key === "ArrowUp") { e.preventDefault(); setPage((p) => clampPage(p - 1)); }
      else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomIn(); }
      else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomOut(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safePageCount]);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-po-text-muted">
        No se pudo abrir el PDF.
      </div>
    );
  }

  return (
    <div className="flex h-full w-full">
      <WorkerThumbnails
        doc={doc}
        pageCount={safePageCount}
        currentPage={page}
        marks={[]}
        onSelect={(p) => setPage(clampPage(p))}
      />
      <div
        ref={panelRef}
        onWheel={onWheel}
        className="relative flex-1 overflow-auto bg-black p-4 flex items-start justify-center"
      >
        {loading || !doc ? (
          <div className="flex h-full items-center justify-center text-sm text-po-text-muted">
            Cargando…
          </div>
        ) : (
          <PdfPage doc={doc} pageNumber={page} scale={effectiveScale} />
        )}
        {doc && !loading && (
          <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg bg-po-panel/90 p-1 shadow-sm ring-1 ring-po-border backdrop-blur">
            <Button size="sm" variant="ghost" icon={ZoomOut} onClick={zoomOut} aria-label="Alejar" />
            <Button size="sm" variant="ghost" icon={Maximize2} onClick={() => setZoom(1)} aria-label="Ajustar a ventana">
              {Math.round(zoom * 100)}%
            </Button>
            <Button size="sm" variant="ghost" icon={ZoomIn} onClick={zoomIn} aria-label="Acercar" />
          </div>
        )}
      </div>
    </div>
  );
}

export default function PDFLightbox() {
  const lightbox = useSessionStore((s) => s.lightbox);
  const closeLightbox = useSessionStore((s) => s.closeLightbox);
  const session = useSessionStore((s) => s.session);
  const savePerFileOverride = useSessionStore((s) => s.savePerFileOverride);
  const scanOcr = useSessionStore((s) => s.scanOcr);
  // Re-fetch after an OCR scan finishes for this cell (G3, review #5/#6).
  const tick = useSessionStore((s) =>
    lightbox ? (s.filesTick[`${lightbox.hospital}|${lightbox.sigla}`] ?? 0) : 0,
  );
  const isScanning = useSessionStore((s) =>
    lightbox ? s.scanningCells.has(`${lightbox.hospital}|${lightbox.sigla}`) : false,
  );
  const [files, setFiles] = useState(null);

  useEffect(() => {
    if (!lightbox) { setFiles(null); return; }
    api.getCellFiles(session.session_id, lightbox.hospital, lightbox.sigla)
      .then(setFiles)
      .catch(() => setFiles([]));
  }, [lightbox?.hospital, lightbox?.sigla, session?.session_id, tick]);

  if (!lightbox || !session) return null;

  const filename = files?.[lightbox.fileIndex]?.name ?? "…";
  const pageCount = files?.[lightbox.fileIndex]?.page_count;
  const pdfUrl = api.cellPdfUrl(session.session_id, lightbox.hospital, lightbox.sigla, lightbox.fileIndex);
  const label = SIGLA_LABELS[lightbox.sigla];
  const showLabel = label && label.toLowerCase() !== lightbox.sigla.toLowerCase();

  return (
    <Dialog open={!!lightbox} onOpenChange={(o) => !o && closeLightbox()}>
      <Dialog.Title className="sr-only">
        Vista previa de PDF: {lightbox.hospital} / {lightbox.sigla} / {filename}
      </Dialog.Title>
      <Dialog.Description className="sr-only">
        Documento PDF con {pageCount ?? "?"} páginas. Use el panel derecho para ajustar el conteo manual o agregar una nota.
      </Dialog.Description>
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
        {lightbox.mode === "count_workers" ? (
          <WorkerCountViewer
            sessionId={session.session_id}
            hospital={lightbox.hospital}
            sigla={lightbox.sigla}
            initialFileIndex={lightbox.fileIndex}
          />
        ) : (
          <>
            <div className="flex-1 overflow-hidden bg-black">
              <InspectView url={pdfUrl} pageCount={pageCount ?? 0} />
            </div>
            <aside className="w-80 border-l border-po-border p-4 overflow-y-auto">
              <FileSummary file={files?.[lightbox.fileIndex]} />
              <Button
                variant="primary"
                icon={ScanSearch}
                size="sm"
                disabled={isScanning}
                onClick={() => scanOcr(session.session_id, [[lightbox.hospital, lightbox.sigla]])}
                className="mt-4 w-full justify-center"
              >
                {isScanning ? "Escaneando…" : "Escanear con OCR"}
              </Button>
              <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual del archivo</h4>
              <div className="flex items-center gap-2">
                <span className="text-sm text-po-text">Documentos:</span>
                <InlineEditCount
                  value={files?.[lightbox.fileIndex]?.effective_count ?? 1}
                  onCommit={(newCount) => {
                    const name = files?.[lightbox.fileIndex]?.name;
                    if (!name) return;
                    setFiles((prev) =>
                      prev?.map((row, idx) =>
                        idx === lightbox.fileIndex
                          ? { ...row, effective_count: newCount, override_count: newCount, origin: "Manual" }
                          : row,
                      ),
                    );
                    savePerFileOverride(session.session_id, lightbox.hospital, lightbox.sigla, name, newCount);
                  }}
                />
              </div>
            </aside>
          </>
        )}
      </Dialog.Body>
    </Dialog>
  );
}
