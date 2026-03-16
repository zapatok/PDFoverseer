import { useState, useRef, useEffect, useCallback } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';

export default function CropSelector({ isOpen, onConfirm, onCancel, testImagePath }) {
  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const transformRef = useRef(null); // store transform API for external buttons
  const [selector, setSelector] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages] = useState(1);
  const [selectionMode, setSelectionMode] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 });
  const [currentScale, setCurrentScale] = useState(1);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  // Reset all state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setSelector(null);
      setImageLoaded(false);
      setIsDragging(false);
      setDragStart(null);
      setSelectionMode(false);
      setCurrentScale(1);
      setShowConfirmDialog(false);
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
    if (!selectionMode) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setDragStart({ x, y });
    setIsDragging(true);
  };

  const handleCanvasMouseMove = (e) => {
    if (!isDragging || !dragStart || !selectionMode) return;
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
  const handleConfirmClick = () => {
    if (!selector) return;
    setShowConfirmDialog(true);
  };

  const handleConfirmYes = () => {
    console.log({ ...selector });
    if (onConfirm) onConfirm(selector);
    setShowConfirmDialog(false);
    if (onCancel) onCancel(); // close panel
  };

  const handleConfirmBack = () => {
    setShowConfirmDialog(false);
  };

  const handleReset = () => {
    setSelector(null);
    if (transformRef.current) {
      transformRef.current.resetTransform();
    }
  };

  const handleCancel = () => {
    if (onCancel) onCancel();
  };

  // --- Canvas rendering (zoom-invariant annotations) ---
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

    // Compensate for zoom so annotations stay visually constant
    const scale = currentScale || 1;
    const invScale = 1 / scale;

    // Selection pixel coords
    const sx = selector.x_start * canvasSize.w;
    const sy = selector.y_start * canvasSize.h;
    const sw = (selector.x_end - selector.x_start) * canvasSize.w;
    const sh = (selector.y_end - selector.y_start) * canvasSize.h;

    // Draw 4 dark rects around selection
    ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    ctx.fillRect(0, 0, canvasSize.w, sy);                          // top
    ctx.fillRect(0, sy + sh, canvasSize.w, canvasSize.h - sy - sh); // bottom
    ctx.fillRect(0, sy, sx, sh);                                    // left
    ctx.fillRect(sx + sw, sy, canvasSize.w - sx - sw, sh);          // right

    // Selection border — zoom-invariant
    ctx.strokeStyle = '#89b4fa';
    ctx.lineWidth = 2 * invScale;
    ctx.strokeRect(sx, sy, sw, sh);

    // Corner coordinate labels — zoom-invariant font
    const fontSize = Math.round(10 * invScale);
    const fontSizeBold = Math.round(13 * invScale);
    const padX = 3 * invScale;
    const padY = 7 * invScale;
    const offsetAbove = 10 * invScale;
    const offsetBelow = 14 * invScale;
    const labelH = 14 * invScale;

    ctx.font = `${fontSize}px monospace`;
    const corners = [
      { text: `${selector.x_start.toFixed(2)}, ${selector.y_start.toFixed(2)}`, x: sx, y: sy - offsetAbove },
      { text: `${selector.x_end.toFixed(2)}, ${selector.y_start.toFixed(2)}`, x: sx + sw, y: sy - offsetAbove },
      { text: `${selector.x_start.toFixed(2)}, ${selector.y_end.toFixed(2)}`, x: sx, y: sy + sh + offsetBelow },
      { text: `${selector.x_end.toFixed(2)}, ${selector.y_end.toFixed(2)}`, x: sx + sw, y: sy + sh + offsetBelow },
    ];

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const c of corners) {
      const m = ctx.measureText(c.text);
      ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
      ctx.fillRect(c.x - m.width / 2 - padX, c.y - padY, m.width + padX * 2, labelH);
      ctx.fillStyle = '#cdd6f4';
      ctx.fillText(c.text, c.x, c.y);
    }

    // Center label — area percentage, zoom-invariant
    const areaPct = ((selector.x_end - selector.x_start) * (selector.y_end - selector.y_start) * 100).toFixed(1);
    const centerLabel = `${areaPct}%`;
    ctx.font = `bold ${fontSizeBold}px monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const cx = sx + sw / 2;
    const cy = sy + sh / 2;
    const cm = ctx.measureText(centerLabel);
    const cPadX = 5 * invScale;
    const cPadY = 9 * invScale;
    const cH = 18 * invScale;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
    ctx.fillRect(cx - cm.width / 2 - cPadX, cy - cPadY, cm.width + cPadX * 2, cH);
    ctx.fillStyle = '#cdd6f4';
    ctx.fillText(centerLabel, cx, cy);
  }, [selector, imageLoaded, canvasSize, currentScale]);

  if (!isOpen) return null;

  // Shared button base classes
  const btnBase = 'h-8 px-3 rounded text-sm font-medium transition-all duration-150 shrink-0 select-none';
  const btnGhost = `${btnBase} border border-[#313244] bg-[#181825] text-[#a6adc8] hover:bg-[#1e1e2e] hover:text-[#cdd6f4] hover:border-[#45475a] active:bg-[#313244] disabled:opacity-40 disabled:pointer-events-none`;
  const btnIcon = 'h-8 w-8 rounded text-sm font-medium transition-all duration-150 shrink-0 select-none border border-[#313244] bg-[#181825] text-[#a6adc8] hover:bg-[#1e1e2e] hover:text-[#cdd6f4] hover:border-[#45475a] active:bg-[#313244] disabled:opacity-40 disabled:pointer-events-none flex items-center justify-center';

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" style={{ backdropFilter: 'blur(4px)' }}>
      <div className="bg-[#11111b] rounded-xl shadow-2xl w-1/2 h-5/6 flex flex-col overflow-hidden border border-[#313244]/50">

        {/* Header */}
        <div className="flex justify-between items-center px-5 py-3 border-b border-[#313244]/60">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-[#89b4fa]" />
            <h2 className="text-base font-semibold text-[#cdd6f4] tracking-tight">Zona de Escaneo</h2>
          </div>
          <button
            onClick={handleCancel}
            className="w-7 h-7 rounded-md flex items-center justify-center text-[#6c7086] hover:text-[#f38ba8] hover:bg-[#f38ba8]/10 transition-all duration-150"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 1L13 13M1 13L13 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </button>
        </div>

        {/* Canvas Container */}
        <div ref={containerRef} className="flex-1 overflow-hidden bg-[#0a0a14] m-3 rounded-lg flex items-center justify-center relative">
          <TransformWrapper
            initialScale={1}
            minScale={0.5}
            maxScale={6}
            panning={{ disabled: selectionMode }}
            wheel={{ disabled: selectionMode }}
            pinch={{ disabled: selectionMode }}
            centerOnInit={true}
            onTransformed={(_, state) => {
              setCurrentScale(state.scale);
            }}
            onInit={(ref) => {
              transformRef.current = ref;
            }}
          >
            {({ zoomIn, zoomOut, resetTransform, state }) => (
              <>
                <TransformComponent
                  wrapperStyle={{ width: '100%', height: '100%' }}
                  contentStyle={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <canvas
                    ref={canvasRef}
                    onMouseDown={handleCanvasMouseDown}
                    onMouseMove={handleCanvasMouseMove}
                    onMouseUp={handleCanvasMouseUp}
                    onMouseLeave={handleCanvasMouseUp}
                    style={{ cursor: selectionMode ? 'crosshair' : 'grab' }}
                  />
                </TransformComponent>

                {/* Floating zoom controls — bottom-right of viewer */}
                <div className="absolute bottom-2.5 right-2.5 flex items-center gap-0.5 bg-[#11111b]/80 backdrop-blur-sm rounded-lg border border-[#313244]/50 px-1.5 py-1 z-10">
                  <button onClick={() => zoomOut()} className={btnIcon} style={{ border: 'none', background: 'none', width: '28px', height: '28px' }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                  </button>
                  <span className="text-[#6c7086] text-xs w-11 text-center font-mono tabular-nums">
                    {Math.round((state?.scale ?? 1) * 100)}%
                  </span>
                  <button onClick={() => zoomIn()} className={btnIcon} style={{ border: 'none', background: 'none', width: '28px', height: '28px' }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 3v8M3 7h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                  </button>
                  <div className="w-px h-4 bg-[#313244] mx-0.5" />
                  <button
                    onClick={() => resetTransform()}
                    className="text-[#6c7086] hover:text-[#cdd6f4] text-xs px-1.5 py-0.5 font-mono transition-colors"
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
        <div className="border-t border-[#313244]/60 px-5 py-3 flex items-center gap-2">

          {/* Cancel — left side, red */}
          <button onClick={handleCancel} className={`${btnBase} border border-[#45475a] bg-[#181825] text-[#f38ba8] hover:bg-[#f38ba8]/10 hover:border-[#f38ba8]/40 active:bg-[#f38ba8]/20`}>
            Cancelar
          </button>

          <div className="w-px h-5 bg-[#313244]/60" />

          {/* Mode Toggle */}
          <button
            onClick={() => setSelectionMode(!selectionMode)}
            className={`${btnBase} w-28 ${
              selectionMode
                ? 'bg-[#89b4fa]/15 text-[#89b4fa] border border-[#89b4fa]/30 hover:bg-[#89b4fa]/20'
                : 'border border-[#313244] bg-[#181825] text-[#a6adc8] hover:bg-[#1e1e2e] hover:text-[#cdd6f4] hover:border-[#45475a]'
            }`}
          >
            {selectionMode ? 'Seleccionar' : 'Pan / Zoom'}
          </button>

          <div className="w-px h-5 bg-[#313244]/60" />

          {/* Page Navigation */}
          <div className="flex items-center gap-1 shrink-0">
            <button disabled={currentPage === 1} className={btnIcon}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M7.5 2.5L4 6l3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            <div className="flex items-center bg-[#181825] border border-[#313244] rounded h-8 px-1">
              <input
                type="number"
                min="1"
                max={totalPages}
                value={currentPage}
                onChange={(e) => {
                  const v = parseInt(e.target.value);
                  if (!isNaN(v)) setCurrentPage(Math.min(totalPages, Math.max(1, v)));
                }}
                onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
                className="w-7 bg-transparent text-[#cdd6f4] text-xs text-center font-mono outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
              <span className="text-[#585b70] text-xs font-mono">/</span>
              <span className="text-[#585b70] text-xs font-mono w-7 text-center">{totalPages}</span>
            </div>
            <button disabled={currentPage === totalPages} className={btnIcon}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2.5L8 6l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </div>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Reset */}
          <button onClick={handleReset} disabled={!selector} className={btnGhost}>
            Reset
          </button>

          {/* Confirm */}
          <button
            onClick={handleConfirmClick}
            disabled={!selector}
            className={`${btnBase} bg-[#89b4fa] text-[#11111b] hover:bg-[#b4d0fb] active:bg-[#74a8f7] disabled:opacity-40 disabled:pointer-events-none`}
          >
            Confirmar
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]" style={{ backdropFilter: 'blur(2px)' }}>
          <div className="bg-[#1e1e2e] rounded-xl border border-[#313244] shadow-2xl p-6 w-80 flex flex-col gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-[#a6e3a1]" />
              <h3 className="text-sm font-semibold text-[#cdd6f4]">Confirmar coordenadas</h3>
            </div>
            {selector && (
              <div className="bg-[#11111b] rounded-lg p-3 border border-[#313244]/50">
                <div className="text-xs text-[#6c7086] font-mono space-y-1">
                  <div className="flex justify-between">
                    <span>x</span>
                    <span className="text-[#a6adc8]">{selector.x_start.toFixed(3)} &rarr; {selector.x_end.toFixed(3)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>y</span>
                    <span className="text-[#a6adc8]">{selector.y_start.toFixed(3)} &rarr; {selector.y_end.toFixed(3)}</span>
                  </div>
                  <div className="flex justify-between pt-1 border-t border-[#313244]/40">
                    <span>area</span>
                    <span className="text-[#a6adc8]">{((selector.x_end - selector.x_start) * (selector.y_end - selector.y_start) * 100).toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            )}
            <div className="flex gap-2 justify-end">
              <button onClick={handleConfirmBack} className={btnGhost}>
                Volver
              </button>
              <button
                onClick={handleConfirmYes}
                className={`${btnBase} bg-[#a6e3a1] text-[#11111b] hover:bg-[#b8eab3] active:bg-[#94d890]`}
              >
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
