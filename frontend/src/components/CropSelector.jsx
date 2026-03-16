import { useState, useRef, useEffect, useCallback } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';

export default function CropSelector({ isOpen, onConfirm, onCancel, testImagePath }) {
  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const [selector, setSelector] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages] = useState(1);
  const [confirmed, setConfirmed] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 });

  // Reset all state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setConfirmed(false);
      setSelector(null);
      setImageLoaded(false);
      setIsDragging(false);
      setDragStart(null);
      setSelectionMode(false);
    }
  }, [isOpen]);

  // Compute canvas dimensions from container + image aspect ratio
  const computeCanvasSize = useCallback(() => {
    const container = containerRef.current;
    const img = imageRef.current;
    if (!container || !img || !img.complete) return null;

    const cw = container.clientWidth;
    const ch = container.clientHeight;
    const imgAspect = img.naturalWidth / img.naturalHeight;
    const containerAspect = cw / ch;

    if (imgAspect > containerAspect) {
      return { w: cw, h: cw / imgAspect };
    }
    return { w: ch * imgAspect, h: ch };
  }, []);

  // ResizeObserver — adapt canvas when window/container resizes
  useEffect(() => {
    if (!isOpen || !containerRef.current) return;
    const ro = new ResizeObserver(() => {
      const size = computeCanvasSize();
      if (size) setCanvasSize(size);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [isOpen, computeCanvasSize]);

  // Set initial canvas size when image loads
  const handleImageLoad = () => {
    setImageLoaded(true);
    const size = computeCanvasSize();
    if (size) setCanvasSize(size);
  };

  // --- Mouse handlers (selection mode only) ---
  const handleCanvasMouseDown = (e) => {
    if (confirmed || !selectionMode) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setDragStart({ x, y });
    setIsDragging(true);
  };

  const handleCanvasMouseMove = (e) => {
    if (!isDragging || !dragStart || confirmed || !selectionMode) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;

    setSelector({
      x_start: Math.max(0, Math.min(dragStart.x, x)),
      x_end:   Math.min(1, Math.max(dragStart.x, x)),
      y_start: Math.max(0, Math.min(dragStart.y, y)),
      y_end:   Math.min(1, Math.max(dragStart.y, y)),
    });
  };

  const handleCanvasMouseUp = () => {
    setIsDragging(false);
  };

  // --- Actions ---
  const handleConfirm = () => {
    if (!selector) return;
    console.log({ ...selector });
    setConfirmed(true);
    if (onConfirm) onConfirm(selector);
  };

  const handleReset = () => {
    setSelector(null);
    setConfirmed(false);
  };

  const handleCancel = () => {
    if (onCancel) onCancel();
  };

  // --- Canvas rendering ---
  useEffect(() => {
    if (!imageLoaded || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = imageRef.current;
    if (!img || !img.complete || canvasSize.w === 0) return;

    canvas.width = canvasSize.w;
    canvas.height = canvasSize.h;

    // Draw full image
    ctx.drawImage(img, 0, 0, canvasSize.w, canvasSize.h);

    if (!selector) return;

    // Selection pixel coords
    const sx = selector.x_start * canvasSize.w;
    const sy = selector.y_start * canvasSize.h;
    const sw = (selector.x_end - selector.x_start) * canvasSize.w;
    const sh = (selector.y_end - selector.y_start) * canvasSize.h;

    // Draw 4 dark rects around selection (avoids clearRect+clip redraw)
    ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
    ctx.fillRect(0, 0, canvasSize.w, sy);                          // top
    ctx.fillRect(0, sy + sh, canvasSize.w, canvasSize.h - sy - sh); // bottom
    ctx.fillRect(0, sy, sx, sh);                                    // left
    ctx.fillRect(sx + sw, sy, canvasSize.w - sx - sw, sh);          // right

    // Selection border
    ctx.strokeStyle = '#89b4fa';
    ctx.lineWidth = 2;
    ctx.strokeRect(sx, sy, sw, sh);

    // Corner coordinate labels — centered on each corner point
    ctx.font = '10px monospace';
    const corners = [
      { text: `${selector.x_start.toFixed(2)}, ${selector.y_start.toFixed(2)}`, x: sx, y: sy - 10 },
      { text: `${selector.x_end.toFixed(2)}, ${selector.y_start.toFixed(2)}`, x: sx + sw, y: sy - 10 },
      { text: `${selector.x_start.toFixed(2)}, ${selector.y_end.toFixed(2)}`, x: sx, y: sy + sh + 14 },
      { text: `${selector.x_end.toFixed(2)}, ${selector.y_end.toFixed(2)}`, x: sx + sw, y: sy + sh + 14 },
    ];

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const c of corners) {
      const m = ctx.measureText(c.text);
      ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
      ctx.fillRect(c.x - m.width / 2 - 3, c.y - 7, m.width + 6, 14);
      ctx.fillStyle = '#cdd6f4';
      ctx.fillText(c.text, c.x, c.y);
    }

    // Center label — area percentage
    const areaPct = ((selector.x_end - selector.x_start) * (selector.y_end - selector.y_start) * 100).toFixed(1);
    const centerLabel = `${areaPct}%`;
    ctx.font = 'bold 13px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const cx = sx + sw / 2;
    const cy = sy + sh / 2;
    const cm = ctx.measureText(centerLabel);
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(cx - cm.width / 2 - 5, cy - 9, cm.width + 10, 18);
    ctx.fillStyle = '#cdd6f4';
    ctx.fillText(centerLabel, cx, cy);
  }, [selector, imageLoaded, canvasSize]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-base rounded-lg shadow-xl w-1/2 h-5/6 flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center p-4 border-b border-[#313244]">
          <h2 className="text-xl font-bold text-gray-200">Seleccionar Zona de Escaneo</h2>
          <button onClick={handleCancel} className="text-gray-400 hover:text-gray-200 text-2xl">
            ✕
          </button>
        </div>

        {/* Canvas Container */}
        <div ref={containerRef} className="flex-1 overflow-hidden bg-surface m-4 rounded-lg flex items-center justify-center">
          <TransformWrapper
            initialScale={1}
            minScale={0.5}
            maxScale={4}
            panning={{ disabled: selectionMode }}
            wheel={{ disabled: selectionMode }}
            pinch={{ disabled: selectionMode }}
          >
            {({ zoomIn, zoomOut, resetTransform, state }) => (
              <>
                <TransformComponent>
                  <canvas
                    ref={canvasRef}
                    onMouseDown={handleCanvasMouseDown}
                    onMouseMove={handleCanvasMouseMove}
                    onMouseUp={handleCanvasMouseUp}
                    onMouseLeave={handleCanvasMouseUp}
                    style={{ cursor: selectionMode ? (confirmed ? 'default' : 'crosshair') : 'grab' }}
                    className="border border-[#313244]"
                  />
                </TransformComponent>

                {/* Zoom buttons rendered inside children-as-function to access zoomIn/zoomOut */}
                <div className="absolute bottom-3 right-3 flex items-center gap-1 bg-black/60 rounded-lg px-2 py-1 z-10">
                  <button
                    onClick={() => zoomOut()}
                    className="text-gray-300 hover:text-white text-sm px-2 py-0.5"
                  >
                    −
                  </button>
                  <span className="text-gray-400 text-xs w-12 text-center">
                    {Math.round((state?.scale ?? 1) * 100)}%
                  </span>
                  <button
                    onClick={() => zoomIn()}
                    className="text-gray-300 hover:text-white text-sm px-2 py-0.5"
                  >
                    +
                  </button>
                  <button
                    onClick={() => resetTransform()}
                    className="text-gray-400 hover:text-white text-xs px-1.5 py-0.5 ml-1 border-l border-gray-600"
                  >
                    1:1
                  </button>
                </div>
              </>
            )}
          </TransformWrapper>
          <img
            ref={imageRef}
            src={testImagePath}
            onLoad={handleImageLoad}
            style={{ display: 'none' }}
          />
        </div>

        {/* Controls Panel */}
        <div className="border-t border-[#313244] px-4 py-3 flex flex-col gap-2">
          {/* Top row: mode + page nav + coordinates */}
          <div className="flex items-center gap-3">
            {/* Mode Toggle — fixed width, identical padding both states */}
            <button
              onClick={() => setSelectionMode(!selectionMode)}
              className={`h-8 w-32 rounded border text-sm font-medium transition-colors shrink-0 ${
                selectionMode
                  ? 'bg-accent text-base border-accent'
                  : 'bg-panel hover:bg-surface text-gray-300 border-[#313244]'
              }`}
            >
              {selectionMode ? 'Seleccionar' : 'Pan / Zoom'}
            </button>

            <div className="w-px h-6 bg-[#313244]" />

            {/* Page Navigation */}
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                disabled={currentPage === 1}
                className="h-8 w-8 rounded border border-[#313244] bg-panel hover:bg-surface text-gray-300 disabled:opacity-50 text-sm flex items-center justify-center"
              >
                ←
              </button>
              <input
                type="number"
                min="1"
                max={totalPages}
                value={currentPage}
                onChange={(e) => {
                  const v = parseInt(e.target.value);
                  if (!isNaN(v)) setCurrentPage(Math.min(totalPages, Math.max(1, v)));
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.target.blur();
                  }
                }}
                className="h-8 w-12 rounded border border-[#313244] bg-panel text-gray-300 text-sm text-center"
              />
              <span className="text-gray-500 text-xs">/ {totalPages}</span>
              <button
                disabled={currentPage === totalPages}
                className="h-8 w-8 rounded border border-[#313244] bg-panel hover:bg-surface text-gray-300 disabled:opacity-50 text-sm flex items-center justify-center"
              >
                →
              </button>
            </div>

            <div className="w-px h-6 bg-[#313244]" />

            {/* Coordinate Display */}
            <div className="bg-surface px-3 h-8 rounded border border-[#313244] flex items-center flex-1 min-w-0">
              {selector ? (
                <div className="text-xs text-gray-400 font-mono flex gap-4">
                  <span>x: {selector.x_start.toFixed(3)} → {selector.x_end.toFixed(3)}</span>
                  <span>y: {selector.y_start.toFixed(3)} → {selector.y_end.toFixed(3)}</span>
                </div>
              ) : (
                <span className="text-xs text-gray-500 font-mono">Arrastra para seleccionar zona</span>
              )}
            </div>

            {confirmed && selector && (
              <span className="text-green-400 text-xs shrink-0">✓ Capturado</span>
            )}
          </div>

          {/* Bottom row: action buttons — all same h-8 px-3 */}
          <div className="flex gap-2">
            <button
              onClick={handleReset}
              disabled={!selector}
              className="h-8 px-3 rounded border border-[#313244] bg-panel hover:bg-surface text-gray-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Limpiar
            </button>
            <button
              onClick={handleConfirm}
              disabled={!selector || confirmed}
              className="h-8 px-3 rounded bg-accent hover:bg-blue-500 text-base text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Confirmar
            </button>
            <div className="flex-1" />
            <button
              onClick={handleCancel}
              className="h-8 px-3 rounded border border-[#313244] bg-panel hover:bg-surface text-gray-300 text-sm"
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
