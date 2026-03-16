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
  const [selectionMode, setSelectionMode] = useState(true);
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
      setSelectionMode(true);
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
  }, [selector, imageLoaded, canvasSize]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-base rounded-lg shadow-xl w-11/12 h-5/6 flex flex-col">
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
        <div className="border-t border-[#313244] p-4 flex items-center gap-4">
          {/* Mode Toggle */}
          <button
            onClick={() => setSelectionMode(!selectionMode)}
            className={`py-1.5 px-3 rounded border text-sm font-medium transition-colors w-36 shrink-0 ${
              selectionMode
                ? 'bg-accent text-base border-accent'
                : 'bg-panel hover:bg-surface text-gray-300 border-[#313244]'
            }`}
          >
            {selectionMode ? '✓ Seleccionar' : 'Pan / Zoom'}
          </button>

          {/* Page Navigation */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-gray-400 text-sm">Pag {currentPage}/{totalPages}</span>
            <button
              disabled={currentPage === 1}
              className="bg-panel hover:bg-surface text-gray-300 py-1 px-2 rounded border border-[#313244] disabled:opacity-50 text-sm"
            >
              ←
            </button>
            <button
              disabled={currentPage === totalPages}
              className="bg-panel hover:bg-surface text-gray-300 py-1 px-2 rounded border border-[#313244] disabled:opacity-50 text-sm"
            >
              →
            </button>
          </div>

          {/* Coordinate Display */}
          <div className="bg-surface px-3 py-1.5 rounded border border-[#313244] flex-1 min-w-0">
            {selector ? (
              <div className="text-xs text-gray-400 font-mono flex gap-4">
                <span>x: {selector.x_start.toFixed(3)} → {selector.x_end.toFixed(3)}</span>
                <span>y: {selector.y_start.toFixed(3)} → {selector.y_end.toFixed(3)}</span>
              </div>
            ) : (
              <div className="text-xs text-gray-500 font-mono">Arrastra sobre la pagina para seleccionar zona</div>
            )}
          </div>

          {confirmed && selector && (
            <span className="text-green-400 text-xs shrink-0">✓ Capturado</span>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 shrink-0">
            <button
              onClick={handleReset}
              disabled={!selector}
              className="bg-panel hover:bg-surface text-gray-300 py-1.5 px-3 rounded border border-[#313244] text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Limpiar
            </button>
            <button
              onClick={handleConfirm}
              disabled={!selector || confirmed}
              className="bg-accent hover:bg-blue-500 text-base py-1.5 px-4 rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Confirmar
            </button>
            <button
              onClick={handleCancel}
              className="bg-panel hover:bg-surface text-gray-300 py-1.5 px-3 rounded border border-[#313244] text-sm"
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
