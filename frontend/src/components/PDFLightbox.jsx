import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import Dialog from "../ui/Dialog";
import Badge from "../ui/Badge";
import Tooltip from "../ui/Tooltip";
import { FileStack } from "lucide-react";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import OriginChip from "./OriginChip";
import InlineEditCount from "./InlineEditCount";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

import { usePdfDocument } from "../hooks/usePdfDocument";
import { PdfPage } from "./PdfPage";
import { WorkerCountViewer } from "./WorkerCountViewer";

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

function InspectView({ url }) {
  const { doc, numPages, error, loading } = usePdfDocument(url);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-po-text-muted">
        No se pudo abrir el PDF.
      </div>
    );
  }
  if (loading || !doc) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-po-text-muted">
        Cargando…
      </div>
    );
  }
  return (
    <TransformWrapper minScale={0.5} maxScale={4} doubleClick={{ disabled: true }}>
      <TransformComponent
        wrapperClass="!w-full !h-full"
        contentClass="flex flex-col items-center gap-3 p-4"
      >
        {Array.from({ length: numPages }, (_, i) => (
          <PdfPage key={i + 1} doc={doc} pageNumber={i + 1} />
        ))}
      </TransformComponent>
    </TransformWrapper>
  );
}

export default function PDFLightbox() {
  const lightbox = useSessionStore((s) => s.lightbox);
  const closeLightbox = useSessionStore((s) => s.closeLightbox);
  const session = useSessionStore((s) => s.session);
  const savePerFileOverride = useSessionStore((s) => s.savePerFileOverride);
  const [files, setFiles] = useState(null);

  useEffect(() => {
    if (!lightbox) { setFiles(null); return; }
    api.getCellFiles(session.session_id, lightbox.hospital, lightbox.sigla)
      .then(setFiles)
      .catch(() => setFiles([]));
  }, [lightbox?.hospital, lightbox?.sigla, session?.session_id]);

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
              <InspectView url={pdfUrl} />
            </div>
            <aside className="w-80 border-l border-po-border p-4 overflow-y-auto">
              <FileSummary file={files?.[lightbox.fileIndex]} />
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
