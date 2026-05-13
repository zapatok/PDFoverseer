import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useSessionStore } from "../store/session";
import OverridePanel from "./OverridePanel";

export default function PDFLightbox() {
  const { session, lightbox, closeLightbox } = useSessionStore();
  const [files, setFiles] = useState(null);

  useEffect(() => {
    if (!lightbox || !session) {
      setFiles(null);
      return;
    }
    let cancelled = false; // ignore stale responses if lightbox swaps cells
    api
      .getCellFiles(session.session_id, lightbox.hospital, lightbox.sigla)
      .then((data) => {
        if (!cancelled) setFiles(data);
      })
      .catch(() => {
        if (!cancelled) setFiles([]);
      });
    return () => {
      cancelled = true;
    };
  }, [lightbox, session?.session_id]);

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e) => {
      if (e.key === "Escape") closeLightbox();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, closeLightbox]);

  if (!lightbox || !session) return null;

  const { hospital, sigla, fileIndex } = lightbox;
  const cell = session.cells?.[hospital]?.[sigla] || {};
  const file = files?.[fileIndex];
  const pdfUrl = file
    ? api.cellPdfUrl(session.session_id, hospital, sigla, fileIndex)
    : null;

  return (
    <div
      onClick={closeLightbox}
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-8"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-7xl h-full max-h-[90vh] flex flex-col overflow-hidden"
      >
        <header className="flex items-center justify-between px-4 py-2 border-b border-slate-700 text-sm">
          <span className="font-mono">
            {hospital} / {sigla}
            {file && <span className="ml-2 text-slate-400">· {file.name}</span>}
          </span>
          <button onClick={closeLightbox} className="text-slate-400 hover:text-slate-200">
            ✕
          </button>
        </header>
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 bg-slate-950 overflow-hidden">
            {pdfUrl ? (
              <iframe src={pdfUrl} className="w-full h-full" title="PDF preview" />
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">
                {files === null ? "Cargando…" : "Sin PDF"}
              </div>
            )}
          </div>
          <aside className="w-80 border-l border-slate-700 p-4 overflow-y-auto">
            <h3 className="text-sm uppercase text-slate-400 mb-2">Counts</h3>
            <div className="space-y-1 text-sm mb-4">
              <p>
                Filename: <span className="font-mono">{cell.filename_count ?? "—"}</span>
              </p>
              <p>
                OCR: <span className="font-mono">{cell.ocr_count ?? "—"}</span>
              </p>
              {cell.method && <p className="text-xs text-slate-500">via {cell.method}</p>}
            </div>
            <OverridePanel hospital={hospital} sigla={sigla} cell={cell} />
          </aside>
        </div>
      </div>
    </div>
  );
}
