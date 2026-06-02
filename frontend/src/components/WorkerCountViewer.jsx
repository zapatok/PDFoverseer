import { useEffect, useRef, useState } from "react";

import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";

import { api } from "../lib/api";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import { usePdfDocument } from "../hooks/usePdfDocument";
import { useFitScale } from "../hooks/useFitScale";
import { useSpeechNumber } from "../hooks/useSpeechNumber";
import { useSessionStore } from "../store/session";
import { computeWorkerCount, fileSubtotal } from "../lib/worker-count";
import Button from "../ui/Button";
import { PdfPage } from "./PdfPage";
import { WorkerBubble } from "./WorkerBubble";
import { WorkerHud } from "./WorkerHud";

const SAVE_DEBOUNCE_MS = 700;
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.2;

/** La marca de una página concreta de un archivo, o undefined. */
function markFor(marks, filename, page) {
  return (marks[filename] || []).find((m) => m.page === page);
}

export function WorkerCountViewer({ sessionId, hospital, sigla, initialFileIndex }) {
  const saveWorkerCount = useSessionStore((s) => s.saveWorkerCount);
  const saveStatus = useSessionStore(
    (s) => s.pendingSaves[`${hospital}|${sigla}|workers`] ?? "idle",
  );

  // El estado inicial se lee UNA vez del store (no se suscribe a la celda: el
  // visor es dueño de las marcas durante la sesión, igual que OverridePanel).
  const initCell = useSessionStore.getState().session?.cells?.[hospital]?.[sigla];

  const [files, setFiles] = useState(null); // [{name, page_count, ...}] | null
  const [fileIndex, setFileIndex] = useState(initialFileIndex || 0);
  const [pageInFile, setPageInFile] = useState(initCell?.worker_cursor?.page || 1);
  const [marks, setMarks] = useState(() => initCell?.worker_marks || {});
  const [status, setStatus] = useState(initCell?.worker_status || "en_progreso");
  const [pending, setPending] = useState(null); // buffer de dígitos tecleados, o null
  const [micPaused, setMicPaused] = useState(false);
  const [zoom, setZoom] = useState(1);

  // --- carga de la lista de archivos (orden = sorted rglob del backend) ---
  useEffect(() => {
    let alive = true;
    api.getCellFiles(sessionId, hospital, sigla).then((f) => {
      if (alive) setFiles(f);
    });
    return () => { alive = false; };
  }, [sessionId, hospital, sigla]);

  // El cursor restaurado puede apuntar a un archivo o una página que ya no
  // existen (un PDF se renombró o se acortó entre sesiones, spec §6.3). En vez
  // de confiar en el estado crudo, la posición se DERIVA acotada a lo que hay
  // hoy (`fileIdx` aquí, `page` tras los guards): así un cursor obsoleto nunca
  // deja `files[idx]` undefined —que crashearía el render— ni pide una página
  // inexistente. El estado crudo se realinea en la primera navegación.
  const fileIdx = files?.length
    ? Math.min(Math.max(fileIndex, 0), files.length - 1)
    : 0;

  // --- PDF del archivo actual ---
  const pdfUrl = files?.length
    ? api.cellPdfUrl(sessionId, hospital, sigla, fileIdx)
    : null;
  const { doc, error } = usePdfDocument(pdfUrl);
  // El ajuste-a-ventana usa `pageInFile` (estado fuente) porque el `page`
  // acotado se deriva tras los early returns y los hooks deben correr antes;
  // el hook solo lee el tamaño natural, así que un valor transitorio fuera de
  // rango se autocorrige en el siguiente render.
  const { panelRef, fitScale } = useFitScale(doc, Math.max(pageInFile, 1));

  // --- autosave con debounce + flush al cerrar ---
  const flushSave = useDebouncedCallback((m, st, cur) => {
    saveWorkerCount(sessionId, hospital, sigla, { marks: m, status: st, cursor: cur });
  }, SAVE_DEBOUNCE_MS);

  // `latest` recibe, ya pasados los guards, la posición DERIVADA (válida); el
  // efecto de desmontaje la persiste como guardado final.
  const latest = useRef(null);
  useEffect(() => {
    return () => {
      flushSave.cancel();
      if (latest.current) {
        saveWorkerCount(sessionId, hospital, sigla, latest.current);
      }
    };
  }, [sessionId, hospital, sigla, saveWorkerCount, flushSave]);

  // limpia el buffer pendiente al cambiar de página
  useEffect(() => {
    setPending(null);
  }, [fileIndex, pageInFile]);

  // El zoom es por página: al cambiar de página o archivo vuelve a "ajustado".
  useEffect(() => {
    setZoom(1);
  }, [fileIndex, pageInFile]);

  // --- atajos de teclado: un listener estable que delega en una ref fresca ---
  const keyHandler = useRef(null);
  useEffect(() => {
    const h = (e) => keyHandler.current?.(e);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  // --- voz: un número reconocido entra como pendiente, igual que tecleado ---
  const { status: micStatus } = useSpeechNumber({
    enabled: !micPaused,
    onNumber: (n) => setPending(String(n)),
  });

  if (!files) {
    return (
      <div className="flex h-full w-full items-center justify-center text-sm text-po-text-muted">
        Cargando archivos…
      </div>
    );
  }
  if (files.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center p-8 text-center text-sm text-po-text-muted">
        Esta celda no tiene PDFs que contar.
      </div>
    );
  }

  const currentFile = files[fileIdx];
  const pageCount = currentFile.page_count || 0;
  // página acotada al archivo actual, por el mismo motivo que `fileIdx`
  const page = Math.min(Math.max(pageInFile, 1), Math.max(pageCount, 1));
  const fileNames = files.map((f) => f.name);
  const total = computeWorkerCount(marks, fileNames);
  const subtotal = fileSubtotal(marks, currentFile.name);
  const fixed = markFor(marks, currentFile.name, page);

  const bubbleState = pending != null && pending !== "" ? "pending" : fixed ? "fixed" : "empty";
  const bubbleValue = pending != null && pending !== "" ? pending : fixed ? fixed.count : "";

  // posición derivada (siempre válida) — la que se muestra y se persiste
  latest.current = { marks, status, cursor: { file: fileIdx, page } };

  // --- navegación continua ---
  const advance = () => {
    if (page < pageCount) setPageInFile(page + 1);
    else if (fileIdx < files.length - 1) { setFileIndex(fileIdx + 1); setPageInFile(1); }
  };
  const retreat = () => {
    if (page > 1) setPageInFile(page - 1);
    else if (fileIdx > 0) {
      const prev = fileIdx - 1;
      setFileIndex(prev);
      setPageInFile(files[prev].page_count || 1);
    }
  };

  // --- zoom (por página; se resetea en el efecto de cambio de página) ---
  const zoomIn = () => setZoom((z) => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2)));
  const resetZoom = () => setZoom(1);
  const effectiveScale = Math.max(0.1, fitScale * zoom);

  // --- mutaciones de marcas (cada una autosalva) ---
  const fixAndAdvance = () => {
    let nextMarks = marks;
    const n = pending == null || pending === "" ? null : parseInt(pending, 10);
    if (n != null && !Number.isNaN(n)) {
      const others = (marks[currentFile.name] || []).filter((m) => m.page !== page);
      nextMarks = { ...marks, [currentFile.name]: [...others, { page, count: n }] };
      setMarks(nextMarks);
    }
    // cursor tras avanzar
    let nf = fileIdx, np = page;
    if (page < pageCount) np = page + 1;
    else if (fileIdx < files.length - 1) { nf = fileIdx + 1; np = 1; }
    flushSave(nextMarks, status, { file: nf, page: np });
    setPending(null);
    advance();
  };
  const deleteMark = () => {
    const nextMarks = {
      ...marks,
      [currentFile.name]: (marks[currentFile.name] || []).filter((m) => m.page !== page),
    };
    setMarks(nextMarks);
    setPending(null);
    flushSave(nextMarks, status, { file: fileIdx, page });
  };
  const editMark = () => {
    // E recarga al buffer la marca ya fijada; si había dígitos sin fijar, los
    // descarta — "editar la página actual" parte del valor guardado (spec §5.3).
    if (fixed) setPending(String(fixed.count));
  };
  const toggleFinish = () => {
    const next = status === "terminado" ? "en_progreso" : "terminado";
    setStatus(next);
    flushSave(marks, next, { file: fileIdx, page });
  };

  // refresca la ref del teclado con los closures de este render. El visor no
  // tiene ningún <input>, así que captura toda la entrada: los dígitos van al
  // buffer pendiente, Backspace lo corrige, y los atajos de §5.4 a la marca.
  keyHandler.current = (e) => {
    if (e.key === "PageDown") { e.preventDefault(); fixAndAdvance(); }
    else if (e.key === "PageUp") { e.preventDefault(); retreat(); }
    else if (e.key === "Delete") { e.preventDefault(); deleteMark(); }
    else if (e.key === "e" || e.key === "E") { e.preventDefault(); editMark(); }
    else if (e.key === "m" || e.key === "M") { e.preventDefault(); setMicPaused((p) => !p); }
    else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomIn(); }
    else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomOut(); }
    else if (e.key === "Backspace") {
      e.preventDefault();
      setPending((p) => (p && p.length > 1 ? p.slice(0, -1) : null));
    } else if (/^[0-9]$/.test(e.key)) {
      e.preventDefault();
      setPending((p) => ((p ?? "") + e.key).slice(0, 4)); // tope de 4 dígitos
    }
  };

  return (
    <div className="flex h-full w-full">
      <div ref={panelRef} className="relative flex-1 overflow-auto bg-black">
        {/* Un PDF roto no es un dead-end: el HUD y los atajos siguen vivos
            (spec §10) — el error se muestra en el panel y Re Pág / Av Pág
            permiten saltar a otro archivo. */}
        {error ? (
          <div className="flex h-full w-full items-center justify-center p-8 text-center text-sm text-po-text-muted">
            No se pudo abrir este PDF. Usa Re Pág / Av Pág para moverte a otro
            archivo; la celda quedará incompleta.
          </div>
        ) : (
          doc && (
            <div className="flex justify-center p-4">
              <PdfPage doc={doc} pageNumber={page} scale={effectiveScale} />
            </div>
          )
        )}
        <WorkerBubble state={bubbleState} value={bubbleValue} />
        {doc && !error && (
          <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg bg-po-panel/90 p-1 shadow-sm ring-1 ring-po-border backdrop-blur">
            <Button size="sm" variant="ghost" icon={ZoomOut} onClick={zoomOut} aria-label="Alejar" />
            <Button size="sm" variant="ghost" icon={Maximize2} onClick={resetZoom} aria-label="Ajustar a ventana">
              {Math.round(zoom * 100)}%
            </Button>
            <Button size="sm" variant="ghost" icon={ZoomIn} onClick={zoomIn} aria-label="Acercar" />
          </div>
        )}
      </div>
      <WorkerHud
        files={files}
        fileIndex={fileIdx}
        pageInFile={page}
        pageCount={pageCount}
        subtotal={subtotal}
        total={total}
        marks={marks}
        currentFilename={currentFile.name}
        status={status}
        saveStatus={saveStatus}
        micStatus={micStatus}
        onFinish={toggleFinish}
      />
    </div>
  );
}
