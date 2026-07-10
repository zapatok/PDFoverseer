import { useEffect, useRef, useState } from "react";
import { LruCache, prerenderOrder } from "../lib/page-cache";
import { getCachedThumb } from "./WorkerThumbnails";

// Per-document render cache: WeakMap<doc, LruCache>. Key `page@scale@rot`;
// value ImageBitmap (or HTMLCanvasElement fallback). Capacity 6 ≈ the ±2
// window + current at one scale, with slack for a zoom change — sized against
// prerenderOrder's default radius = 2; bumping that radius without bumping
// this capacity degrades the cache to always-cold. Revisit both together.
const RENDER_CACHE = new WeakMap();
const CACHE_CAPACITY = 6;

function cacheFor(doc) {
  let c = RENDER_CACHE.get(doc);
  if (!c) {
    c = new LruCache(CACHE_CAPACITY, (bmp) => bmp?.close?.());
    RENDER_CACHE.set(doc, c);
  }
  return c;
}

/** Deterministically release a doc's cached bitmaps (call before doc.destroy()). */
export function releaseRenderCache(doc) {
  RENDER_CACHE.get(doc)?.clear(); // clear() onEvicts → bmp.close()
  RENDER_CACHE.delete(doc);
}

const keyFor = (page, scale, rotation) => `${page}@${scale}@${rotation}`;

// registerTask lets the caller cancel the in-flight pdf.js RenderTask on
// page/scale change (spec §1: "the existing render-task cancel ... stays").
// The `cancelled` flag alone would only discard the RESULT — the paint work
// would keep burning CPU in the background under rapid page-flipping.
async function renderToBitmap(doc, pageNumber, scale, rotation, registerTask) {
  const page = await doc.getPage(pageNumber);
  try {
    const viewport = page.getViewport({
      scale,
      rotation: ((page.rotate ?? 0) + rotation) % 360,
    });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const task = page.render({ canvasContext: canvas.getContext("2d"), viewport });
    registerTask?.(task);
    await task.promise; // rejects with RenderingCancelledException on cancel
    if (typeof createImageBitmap === "function") {
      const bmp = await createImageBitmap(canvas);
      canvas.width = 0; // release backing store eagerly
      return bmp;
    }
    return canvas; // jsdom / old browsers: drawImage accepts canvases too
  } finally {
    page.cleanup();
  }
}

/**
 * Renderiza una página de un PDF a un canvas, con caché LRU por documento,
 * placeholder instantáneo desde la miniatura y pre-render de la ventana ±2.
 *
 * @param {object} props
 * @param {object} props.doc - PDFDocumentProxy de usePdfDocument.
 * @param {number} props.pageNumber - número de página, 1-indexado.
 * @param {number} [props.scale] - escala de render (1.5 por defecto).
 * @param {number} [props.rotation] - grados extra sobre el /Rotate propio (§4).
 */
export function PdfPage({ doc, pageNumber, scale = 1.5, rotation = 0 }) {
  const canvasRef = useRef(null);
  const [placeholder, setPlaceholder] = useState(null);

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    const cache = cacheFor(doc);
    // Every in-flight pdf.js RenderTask (current page + pre-renders) lands
    // here so cleanup can .cancel() them — not just ignore their results.
    const liveTasks = new Set();
    const track = (task) => {
      liveTasks.add(task);
      // Late registration: if cleanup already ran (cancelled), the liveTasks
      // sweep missed this task — cancel it on arrival.
      if (cancelled) task.cancel();
      task.promise.catch(() => {}).finally(() => liveTasks.delete(task));
    };

    const draw = (bmp) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = bmp.width;
      canvas.height = bmp.height;
      canvas.getContext("2d").drawImage(bmp, 0, 0);
      setPlaceholder(null);
    };

    const cached = cache.get(keyFor(pageNumber, scale, rotation));
    if (cached) {
      draw(cached); // synchronous hit — no flash
    } else {
      // Instant placeholder from the thumbnail cache while the real render runs.
      setPlaceholder(getCachedThumb(doc, pageNumber));
      renderToBitmap(doc, pageNumber, scale, rotation, track)
        .then((bmp) => {
          if (cancelled) {
            bmp?.close?.();
            return;
          }
          cache.set(keyFor(pageNumber, scale, rotation), bmp);
          draw(bmp);
        })
        .catch(() => {}); // RenderingCancelledException / detached doc
    }

    // Pre-render window, low priority, after the current page settled.
    const idle = window.requestIdleCallback ?? ((fn) => setTimeout(fn, 150));
    const cancelIdle = window.cancelIdleCallback ?? clearTimeout;
    const handle = idle(async () => {
      const total = doc.numPages ?? 0;
      for (const p of prerenderOrder(pageNumber, total)) {
        if (cancelled) return;
        const k = keyFor(p, scale, rotation);
        if (cache.get(k)) continue;
        try {
          const bmp = await renderToBitmap(doc, p, scale, rotation, track);
          if (cancelled) {
            bmp?.close?.();
            return;
          }
          cache.set(k, bmp);
        } catch {
          return; // cancelled / doc closed mid-prerender — stop quietly
        }
      }
    });

    return () => {
      cancelled = true;
      cancelIdle(handle);
      // Spec §1: cancel semantics preserved — kill in-flight paints, current
      // and pre-render alike (the old PdfPage cancelled its single task too).
      for (const task of liveTasks) task.cancel();
    };
  }, [doc, pageNumber, scale, rotation]);

  return (
    <div className="relative">
      {placeholder && (
        <img
          src={placeholder}
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full blur-[2px] opacity-70"
        />
      )}
      <canvas ref={canvasRef} className="block max-w-full shadow-sm ring-1 ring-po-border" />
    </div>
  );
}
