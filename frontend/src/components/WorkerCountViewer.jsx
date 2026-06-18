import { useEffect, useRef, useState } from "react";

import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";

import { api } from "../lib/api";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import { usePdfDocument } from "../hooks/usePdfDocument";
import { useFitScale } from "../hooks/useFitScale";
import { useSpeechNumber } from "../hooks/useSpeechNumber";
import { useSessionStore } from "../store/session";
import { computeWorkerCount, fileSubtotal } from "../lib/worker-count";
import { countTypeFor } from "../lib/sigla-info";
import { isValidRange, normalizeRange } from "../lib/reorg-range";
import Button from "../ui/Button";
import Badge from "../ui/Badge";
import { PdfPage } from "./PdfPage";
import { WorkerBubble } from "./WorkerBubble";
import { WorkerHud } from "./WorkerHud";
import { WorkerThumbnails } from "./WorkerThumbnails";

const SAVE_DEBOUNCE_MS = 700;
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.2;

// Hospitals and siglas for the reorg destination picker.
const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];
const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts", "art",
  "insgral", "bodega", "maquinaria", "ext", "senal", "exc", "altura",
  "caliente", "herramientas_elec", "andamios", "chps",
];

/** La marca de una página concreta de un archivo, o undefined. */
function markFor(marks, filename, page) {
  return (marks[filename] || []).find((m) => m.page === page);
}

/**
 * Columna de miniaturas con resaltado de rango de reorg.
 * Extiende WorkerThumbnails visualmente con un fondo de selección en el rango.
 */
function ReorgThumbnails({ doc, pageCount, currentPage, reorgStart, reorgEnd, onSelect }) {
  const refs = useRef({});
  const currentRef = useRef(null);

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "nearest" });
  }, [currentPage]);

  if (!doc || !pageCount) {
    return <aside aria-hidden="true" className="w-28 shrink-0 border-r border-po-border bg-po-panel" />;
  }

  const inRange = (p) =>
    reorgStart != null && reorgEnd != null && p >= reorgStart && p <= reorgEnd;
  const isStart = (p) => p === reorgStart;
  const isEnd = (p) => p === reorgEnd;

  return (
    <aside className="w-28 shrink-0 overflow-y-auto border-r border-po-border bg-po-panel p-1.5">
      <ul className="flex flex-col gap-1.5">
        {Array.from({ length: pageCount }, (_, i) => i + 1).map((p) => (
          <li
            key={p}
            ref={(el) => {
              refs.current[p] = el;
              if (p === currentPage) currentRef.current = el;
            }}
          >
            <button
              onClick={() => onSelect(p)}
              aria-current={p === currentPage ? "true" : undefined}
              aria-label={`Página ${p}${isStart(p) ? " (inicio)" : ""}${isEnd(p) ? " (fin)" : ""}`}
              className={[
                "relative block w-full rounded border p-0.5 transition",
                p === currentPage
                  ? "border-po-accent ring-1 ring-po-accent"
                  : inRange(p)
                    ? "border-po-scanning bg-po-scanning-bg"
                    : "border-po-border hover:border-po-border-strong",
              ].join(" ")}
            >
              <div className="flex aspect-[3/4] w-full items-center justify-center bg-po-bg text-[10px] text-po-text-subtle">
                …
              </div>
              <span className="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] tabular-nums text-white">
                {p}
              </span>
              {(isStart(p) || isEnd(p)) && (
                <span className="absolute right-1 top-1 rounded-full bg-po-scanning px-1 text-[10px] font-medium text-white">
                  {isStart(p) ? "A" : "Z"}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

/**
 * HUD lateral del modo reorganización: selección de rango + destino + crear op.
 */
function ReorgHud({
  currentPage,
  pageCount,
  reorgStart,
  reorgEnd,
  onMarkStart,
  onMarkEnd,
  onClearRange,
  onCreateOp,
  currentFile,
  sourceHospital,
  sourceSigla,
}) {
  const [opType, setOpType] = useState("extract_pages");
  const [destHospital, setDestHospital] = useState(HOSPITALS[0]);
  const [destSigla, setDestSigla] = useState(SIGLAS[0]);
  const [rotDeg, setRotDeg] = useState(0);
  const [creating, setCreating] = useState(false);

  const rangeValid = isValidRange(reorgStart, reorgEnd, pageCount);
  const canCreate =
    rangeValid &&
    currentFile != null &&
    (opType === "split_in_place" || opType === "rotate"
      ? true
      : destHospital !== sourceHospital || destSigla !== sourceSigla);

  const handleCreate = async () => {
    if (!canCreate) return;
    const [start, end] = normalizeRange(reorgStart, reorgEnd);
    const opDraft = {
      op_type: opType,
      source: {
        file: currentFile,
        page_range: [start, end],
      },
      dest: { hospital: destHospital, sigla: destSigla },
      doc_count: null,
      worker_count: null,
      rotation_deg: opType === "rotate" ? rotDeg : 0,
    };
    setCreating(true);
    try {
      await onCreateOp(opDraft);
      onClearRange();
    } finally {
      setCreating(false);
    }
  };

  const selectClass =
    "w-full rounded border border-po-border bg-po-panel px-2 py-1 text-xs text-po-text focus:outline-none focus:ring-1 focus:ring-po-accent";

  return (
    <aside className="flex w-52 shrink-0 flex-col gap-3 overflow-y-auto border-l border-po-border bg-po-panel p-3 text-xs">
      <div className="font-semibold text-po-text">Reorganizar rango</div>

      {/* Archivo actual */}
      <div className="truncate text-[10px] text-po-text-muted" title={currentFile}>
        {currentFile ?? "—"}
      </div>

      {/* Marcar inicio / fin */}
      <div className="flex flex-col gap-1.5">
        <Button
          size="sm"
          variant={reorgStart != null ? "primary" : "secondary"}
          onClick={onMarkStart}
        >
          {reorgStart != null ? `Inicio: pág. ${reorgStart}` : "Marcar inicio"}
        </Button>
        <Button
          size="sm"
          variant={reorgEnd != null ? "primary" : "secondary"}
          onClick={onMarkEnd}
        >
          {reorgEnd != null ? `Fin: pág. ${reorgEnd}` : "Marcar fin"}
        </Button>
        {(reorgStart != null || reorgEnd != null) && (
          <button
            className="text-[10px] text-po-text-muted underline hover:text-po-text"
            onClick={onClearRange}
          >
            Limpiar selección
          </button>
        )}
      </div>

      {/* Estado del rango */}
      {reorgStart != null && reorgEnd != null && (
        <div className="rounded border border-po-border bg-po-bg px-2 py-1 text-[10px]">
          {rangeValid ? (
            <span className="text-po-confidence-high">
              Páginas {Math.min(reorgStart, reorgEnd)}–{Math.max(reorgStart, reorgEnd)}
            </span>
          ) : (
            <span className="text-po-error">Rango inválido</span>
          )}
        </div>
      )}

      {/* Tipo de operación */}
      <div className="flex flex-col gap-1">
        <label className="text-[10px] font-medium text-po-text-muted">Tipo de operación</label>
        <select className={selectClass} value={opType} onChange={(e) => setOpType(e.target.value)}>
          <option value="extract_pages">Extraer páginas</option>
          <option value="split_in_place">Dividir en celda</option>
          <option value="rotate">Rotar</option>
        </select>
      </div>

      {/* Destino (no aplica para split_in_place ni rotate) */}
      {opType === "extract_pages" && (
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium text-po-text-muted">Destino</label>
          <select
            className={selectClass}
            value={destHospital}
            onChange={(e) => setDestHospital(e.target.value)}
          >
            {HOSPITALS.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
          <select
            className={selectClass}
            value={destSigla}
            onChange={(e) => setDestSigla(e.target.value)}
          >
            {SIGLAS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          {destHospital === sourceHospital && destSigla === sourceSigla && (
            <span className="text-[10px] text-po-error">
              El destino debe ser diferente al origen.
            </span>
          )}
        </div>
      )}

      {/* Rotación (solo para rotate) */}
      {opType === "rotate" && (
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium text-po-text-muted">Rotación</label>
          <select
            className={selectClass}
            value={rotDeg}
            onChange={(e) => setRotDeg(Number(e.target.value))}
          >
            <option value={90}>90°</option>
            <option value={180}>180°</option>
            <option value={270}>270°</option>
          </select>
        </div>
      )}

      {/* Crear operación */}
      <Button
        size="sm"
        variant="primary"
        disabled={!canCreate || creating}
        onClick={handleCreate}
      >
        {creating ? "Creando…" : "Crear operación"}
      </Button>

      {/* Chips informativas de la selección activa */}
      {rangeValid && (
        <div className="flex flex-wrap gap-1">
          <Badge variant="blue">{opType}</Badge>
        </div>
      )}
    </aside>
  );
}

export function WorkerCountViewer({
  sessionId,
  hospital,
  sigla,
  initialFileIndex,
  mode = "worker",
  onCreateOp,
}) {
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

  // Reorg-mode state: page range selection (1-based; null = not yet marked).
  const [reorgStartPage, setReorgStartPage] = useState(null);
  const [reorgEndPage, setReorgEndPage] = useState(null);

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
  // GATE: both the debounced save and the unmount flush are skipped in reorg
  // mode — no worker marks should be POSTed to the worker-count endpoint when
  // the viewer is in range-selection mode.
  const flushSave = useDebouncedCallback((m, st, cur) => {
    if (mode === "reorg") return;
    saveWorkerCount(sessionId, hospital, sigla, { marks: m, status: st, cursor: cur });
  }, SAVE_DEBOUNCE_MS);

  // `latest` recibe, ya pasados los guards, la posición DERIVADA (válida); el
  // efecto de desmontaje la persiste como guardado final.
  const latest = useRef(null);
  useEffect(() => {
    return () => {
      flushSave.cancel();
      // GATE: skip unmount flush in reorg mode — prevent stale marks from being
      // POSTed when closing the reorg viewer.
      if (mode === "reorg") return;
      if (latest.current) {
        saveWorkerCount(sessionId, hospital, sigla, latest.current);
      }
    };
  }, [sessionId, hospital, sigla, saveWorkerCount, flushSave, mode]);

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

  // count_type determina si este visor opera en modo "trabajadores" (voice on,
  // label "trabajadores") o modo "chequeos" (sin voz, label "chequeos").
  const countType = countTypeFor(sigla);
  const isWorkersMode = countType === "documents_workers";
  const unit = isWorkersMode ? "trabajadores" : "chequeos";

  // --- voz: un número reconocido entra como pendiente, igual que tecleado ---
  // El hook se llama siempre (Rules-of-Hooks); se desactiva vía `enabled`.
  const { status: micStatus } = useSpeechNumber({
    enabled: !micPaused && isWorkersMode && mode === "worker",
    onNumber: (n) => {
      if (mode === "reorg") return;
      setPending(String(n));
    },
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
  // Incr J: add reorg_worker_delta so the viewer total matches the cell total.
  // initCell is snapshotted at mount; the delta is stable during a counting
  // session (reorg ops aren't created while the viewer is open).
  const total = computeWorkerCount(marks, fileNames) + (initCell?.reorg_worker_delta ?? 0);
  const subtotal = fileSubtotal(marks, currentFile.name);
  const fixed = markFor(marks, currentFile.name, page);

  const bubbleState = pending != null && pending !== "" ? "pending" : fixed ? "fixed" : "empty";
  const bubbleValue = pending != null && pending !== "" ? pending : fixed ? fixed.count : "";

  // posición derivada (siempre válida) — la que se muestra y se persiste.
  // En reorg mode no se persiste nada de trabajadores (gate del unmount flush);
  // no escribir `latest.current` aquí deja explícito que reorg no toca marcas.
  if (mode !== "reorg") {
    latest.current = { marks, status, cursor: { file: fileIdx, page } };
  }

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
  // GATE: in reorg mode the keyboard handler is a no-op — digits/PageDown must
  // NOT write worker marks while the operator is selecting a page range.
  keyHandler.current = (e) => {
    if (mode === "reorg") return;
    if (e.key === "PageDown") { e.preventDefault(); fixAndAdvance(); }
    else if (e.key === "PageUp") { e.preventDefault(); retreat(); }
    else if (e.key === "Delete") { e.preventDefault(); deleteMark(); }
    else if (e.key === "e" || e.key === "E") { e.preventDefault(); editMark(); }
    else if ((e.key === "m" || e.key === "M") && isWorkersMode) { e.preventDefault(); setMicPaused((p) => !p); }
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

  // --- reorg-mode helpers ---
  const handleMarkStart = () => setReorgStartPage(page);
  const handleMarkEnd = () => setReorgEndPage(page);
  const handleClearRange = () => { setReorgStartPage(null); setReorgEndPage(null); };

  const handleCreateOp = async (opDraft) => {
    if (onCreateOp) {
      await onCreateOp(opDraft);
    }
  };

  return (
    <div className="flex h-full w-full">
      {mode === "reorg" ? (
        <ReorgThumbnails
          doc={error ? null : doc}
          pageCount={pageCount}
          currentPage={page}
          reorgStart={reorgStartPage}
          reorgEnd={reorgEndPage}
          onSelect={setPageInFile}
        />
      ) : (
        <WorkerThumbnails
          doc={error ? null : doc}
          pageCount={pageCount}
          currentPage={page}
          marks={marks[currentFile.name] || []}
          onSelect={setPageInFile}
          unit={unit}
        />
      )}
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
        {/* Worker bubble only in worker mode */}
        {mode === "worker" && <WorkerBubble state={bubbleState} value={bubbleValue} />}
        {doc && !error && (
          <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg bg-po-panel/90 p-1 shadow-sm ring-1 ring-po-border backdrop-blur">
            <Button size="sm" variant="ghost" icon={ZoomOut} onClick={zoomOut} aria-label="Alejar" />
            <Button size="sm" variant="ghost" icon={Maximize2} onClick={resetZoom} aria-label="Ajustar a ventana">
              {Math.round(zoom * 100)}%
            </Button>
            <Button size="sm" variant="ghost" icon={ZoomIn} onClick={zoomIn} aria-label="Acercar" />
          </div>
        )}
        {/* Reorg mode: page indicator overlay */}
        {mode === "reorg" && (
          <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-lg bg-po-panel/90 px-2 py-1 text-xs text-po-text-muted shadow-sm ring-1 ring-po-border backdrop-blur">
            Pág. {page} / {pageCount}
          </div>
        )}
      </div>
      {mode === "worker" ? (
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
          unit={unit}
          showMic={isWorkersMode}
        />
      ) : (
        <ReorgHud
          currentPage={page}
          pageCount={pageCount}
          reorgStart={reorgStartPage}
          reorgEnd={reorgEndPage}
          onMarkStart={handleMarkStart}
          onMarkEnd={handleMarkEnd}
          onClearRange={handleClearRange}
          onCreateOp={handleCreateOp}
          currentFile={currentFile.name}
          sourceHospital={hospital}
          sourceSigla={sigla}
        />
      )}
    </div>
  );
}
