import { useEffect, useRef, useState } from "react";

// Cache de miniaturas: WeakMap sobre el objeto `doc` → Map(page → dataURL).
// Al cambiar de archivo `doc` es otro objeto, así que el cache se invalida solo.
const THUMB_CACHE = new WeakMap();
const THUMB_WIDTH = 110; // px de ancho del raster (+20%, triage I1)

function cacheFor(doc) {
  let m = THUMB_CACHE.get(doc);
  if (!m) {
    m = new Map();
    THUMB_CACHE.set(doc, m);
  }
  return m;
}

/**
 * Read-only peek for PdfPage's instant placeholder (spec §1).
 *
 * Caveat: looks up only the plain numeric (unrotated) key, so a page under an
 * active rotate op usually gets NO placeholder (full miss), not a
 * stale-orientation one — expected, tiny impact (~100 ms of blank).
 */
export function getCachedThumb(doc, pageNumber) {
  return THUMB_CACHE.get(doc)?.get(pageNumber) ?? null;
}

function Thumb({ doc, pageNumber, active, count, onSelect, unit = "trabajadores", rotation = 0 }) {
  const ref = useRef(null);
  // Composite cache key only when rotated — unrotated pages keep the plain
  // numeric key so existing (pre-rotation) cache entries stay valid.
  const cacheKey = rotation ? `${pageNumber}@${rotation}` : pageNumber;
  const [url, setUrl] = useState(() => cacheFor(doc).get(cacheKey) || null);

  useEffect(() => {
    if (url) return undefined; // ya cacheada
    const el = ref.current;
    if (!el) return undefined;
    let cancelled = false;
    const io = new IntersectionObserver((entries) => {
      if (!entries[0]?.isIntersecting) return;
      io.disconnect();
      doc.getPage(pageNumber).then((page) => {
        if (cancelled) {
          page.cleanup();
          return;
        }
        const rot = ((page.rotate ?? 0) + rotation) % 360;
        const base = page.getViewport({ scale: 1, rotation: rot });
        const v = page.getViewport({ scale: THUMB_WIDTH / base.width, rotation: rot });
        const canvas = document.createElement("canvas");
        canvas.width = v.width;
        canvas.height = v.height;
        const task = page.render({ canvasContext: canvas.getContext("2d"), viewport: v });
        task.promise
          .then(() => {
            const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
            cacheFor(doc).set(cacheKey, dataUrl);
            page.cleanup();
            if (!cancelled) setUrl(dataUrl);
          })
          .catch(() => page.cleanup());
      });
    });
    io.observe(el);
    return () => {
      cancelled = true;
      io.disconnect();
    };
  }, [doc, pageNumber, url, cacheKey, rotation]);

  return (
    <button
      ref={ref}
      onClick={() => onSelect(pageNumber)}
      aria-current={active ? "true" : undefined}
      aria-label={`Página ${pageNumber}${count != null ? `, ${count} ${unit}` : ""}`}
      className={[
        "relative block w-full rounded border p-0.5 transition",
        active
          ? "border-po-accent ring-1 ring-po-accent"
          : "border-po-border hover:border-po-border-strong",
      ].join(" ")}
    >
      {url ? (
        <img src={url} alt="" className="block w-full rounded-sm" />
      ) : (
        <div className="flex aspect-[3/4] w-full items-center justify-center bg-po-bg text-[10px] text-po-text-subtle">
          …
        </div>
      )}
      <span className="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] tabular-nums text-white">
        {pageNumber}
      </span>
      {count != null && (
        <span className="absolute right-1 top-1 rounded-full bg-po-confidence-high-bg px-1 text-[10px] font-medium tabular-nums text-po-confidence-high">
          {count}
        </span>
      )}
    </button>
  );
}

/**
 * Columna vertical de miniaturas del PDF actual.
 *
 * @param {object} props
 * @param {object|null} props.doc - PDFDocumentProxy actual (null si error/sin cargar).
 * @param {number} props.pageCount
 * @param {number} props.currentPage
 * @param {{page:number,count:number}[]} props.marks - marcas del archivo actual.
 * @param {(page:number)=>void} props.onSelect
 * @param {string} [props.unit] - "trabajadores" | "chequeos" (label del aria-label por página).
 * @param {(page:number)=>number} [props.rotationForPage] - grados extra por página (§4), null si no aplica.
 */
export function WorkerThumbnails({
  doc,
  pageCount,
  currentPage,
  marks,
  onSelect,
  unit = "trabajadores",
  rotationForPage = null,
}) {
  const countByPage = new Map((marks || []).map((m) => [m.page, m.count]));
  const currentRef = useRef(null);

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "center" });
  }, [currentPage]);

  if (!doc || !pageCount) {
    return <aside aria-hidden="true" className="w-32 shrink-0 border-r border-po-border bg-po-panel" />;
  }

  return (
    <aside className="w-32 shrink-0 overflow-y-auto border-r border-po-border bg-po-panel p-1.5">
      <ul className="flex flex-col gap-1.5">
        {Array.from({ length: pageCount }, (_, i) => i + 1).map((p) => {
          const rotation = rotationForPage ? rotationForPage(p) : 0;
          return (
            // Key by page@rotation (Thumb's cache key): a live rotation change
            // (op created/deleted/retired mid-session) remounts Thumb, whose
            // lazy `url` init then reads the RIGHT cache slot — otherwise the
            // `if (url)` guard in its effect would keep the stale orientation.
            <li key={rotation ? `${p}@${rotation}` : p} ref={p === currentPage ? currentRef : null}>
              <Thumb
                doc={doc}
                pageNumber={p}
                active={p === currentPage}
                count={countByPage.has(p) ? countByPage.get(p) : null}
                onSelect={onSelect}
                rotation={rotation}
              />
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
