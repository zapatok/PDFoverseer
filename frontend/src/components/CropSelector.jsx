import { useState, useRef, useEffect, useCallback } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';

export default function CropSelector({ isOpen, onConfirm, onCancel, testImagePath }) {
  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const transformRef = useRef(null);
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

  useEffect(() => {
    if (!isOpen || !containerRef.current) return;
    const ro = new ResizeObserver(() => {
      const size = computeCanvasSize();
      if (size) setCanvasSize(size);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [isOpen, computeCanvasSize]);

  const handleImageLoad = () => {
    setImageLoaded(true);
    const size = computeCanvasSize();
    if (size) setCanvasSize(size);
  };

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

  const handleCanvasMouseUp = () => setIsDragging(false);

  const handleConfirmClick = () => {
    if (!selector) return;
    setShowConfirmDialog(true);
  };

  const handleConfirmYes = () => {
    console.log({ ...selector });
    if (onConfirm) onConfirm(selector);
    setShowConfirmDialog(false);
    if (onCancel) onCancel();
  };

  const handleConfirmBack = () => setShowConfirmDialog(false);

  const handleReset = () => {
    setSelector(null);
    if (transformRef.current) transformRef.current.resetTransform();
  };

  const handleCancel = () => { if (onCancel) onCancel(); };

  // --- Canvas rendering (zoom-invariant annotations) ---
  useEffect(() => {
    if (!imageLoaded || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = imageRef.current;
    if (!img || !img.complete || canvasSize.w === 0) return;

    canvas.width = canvasSize.w;
    canvas.height = canvasSize.h;
    ctx.drawImage(img, 0, 0, canvasSize.w, canvasSize.h);

    if (!selector) return;

    const scale = currentScale || 1;
    const inv = 1 / scale;

    const sx = selector.x_start * canvasSize.w;
    const sy = selector.y_start * canvasSize.h;
    const sw = (selector.x_end - selector.x_start) * canvasSize.w;
    const sh = (selector.y_end - selector.y_start) * canvasSize.h;

    // Dark overlay around selection
    ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    ctx.fillRect(0, 0, canvasSize.w, sy);
    ctx.fillRect(0, sy + sh, canvasSize.w, canvasSize.h - sy - sh);
    ctx.fillRect(0, sy, sx, sh);
    ctx.fillRect(sx + sw, sy, canvasSize.w - sx - sw, sh);

    // Selection border
    ctx.strokeStyle = '#89b4fa';
    ctx.lineWidth = 2 * inv;
    ctx.strokeRect(sx, sy, sw, sh);

    // Zoom-invariant label dimensions
    const fs = Math.round(10 * inv);
    const fsBold = Math.round(13 * inv);
    const px = 3 * inv;
    const py = 7 * inv;
    const above = 10 * inv;
    const below = 14 * inv;
    const lh = 14 * inv;

    // Corner labels
    ctx.font = `${fs}px Inter, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const corners = [
      { text: `${selector.x_start.toFixed(2)}, ${selector.y_start.toFixed(2)}`, x: sx, y: sy - above },
      { text: `${selector.x_end.toFixed(2)}, ${selector.y_start.toFixed(2)}`, x: sx + sw, y: sy - above },
      { text: `${selector.x_start.toFixed(2)}, ${selector.y_end.toFixed(2)}`, x: sx, y: sy + sh + below },
      { text: `${selector.x_end.toFixed(2)}, ${selector.y_end.toFixed(2)}`, x: sx + sw, y: sy + sh + below },
    ];
    for (const c of corners) {
      const m = ctx.measureText(c.text);
      ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
      ctx.fillRect(c.x - m.width / 2 - px, c.y - py, m.width + px * 2, lh);
      ctx.fillStyle = '#cdd6f4';
      ctx.fillText(c.text, c.x, c.y);
    }

    // Center area percentage
    const areaPct = ((selector.x_end - selector.x_start) * (selector.y_end - selector.y_start) * 100).toFixed(1);
    ctx.font = `600 ${fsBold}px Inter, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const cx = sx + sw / 2;
    const cy = sy + sh / 2;
    const cm = ctx.measureText(`${areaPct}%`);
    const cpx = 5 * inv;
    const cpy = 9 * inv;
    const ch2 = 18 * inv;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
    ctx.fillRect(cx - cm.width / 2 - cpx, cy - cpy, cm.width + cpx * 2, ch2);
    ctx.fillStyle = '#cdd6f4';
    ctx.fillText(`${areaPct}%`, cx, cy);
  }, [selector, imageLoaded, canvasSize, currentScale]);

  if (!isOpen) return null;

  // Instruction bar content per mode
  const modeLabel = selectionMode ? 'MODO SELECCIONAR' : 'MODO ZOOM/PAN';
  const modeHint = selectionMode
    ? 'Arrastra sobre el documento para delimitar la zona'
    : 'Scroll para zoom, arrastra para mover';

  // Shared button styles — all h-8, consistent font
  const btn = 'h-8 px-3 rounded text-sm transition-all duration-150 shrink-0 select-none font-sans';
  const btnGhost = `${btn} border border-[#313244] bg-[#181825] text-[#a6adc8] hover:bg-[#1e1e2e] hover:text-[#cdd6f4] hover:border-[#45475a] active:bg-[#313244] disabled:opacity-40 disabled:pointer-events-none`;
  const btnIcon = 'h-8 w-8 rounded text-sm transition-all duration-150 shrink-0 select-none border border-[#313244] bg-[#181825] text-[#a6adc8] hover:bg-[#1e1e2e] hover:text-[#cdd6f4] hover:border-[#45475a] active:bg-[#313244] disabled:opacity-40 disabled:pointer-events-none flex items-center justify-center';

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" style={{ backdropFilter: 'blur(4px)' }}>
      <div className="bg-[#11111b] rounded-xl shadow-2xl w-1/2 h-5/6 flex flex-col overflow-hidden border border-[#313244]/50">

        {/* Header */}
        <div className="flex justify-between items-center px-5 py-3 border-b border-[#313244]/60">
          <h2 className="text-2xl font-bold text-gray-100">
            Esc&aacute;ner
          </h2>
          <button
            onClick={handleCancel}
            className="w-7 h-7 rounded-md flex items-center justify-center text-[#6c7086] hover:text-[#f38ba8] hover:bg-[#f38ba8]/10 transition-all duration-150"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 1L13 13M1 13L13 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </button>
        </div>

        {/* Instruction bar */}
        <div className={`px-5 py-1.5 text-xs border-b transition-colors duration-200 flex items-center gap-2 ${
          selectionMode
            ? 'bg-[#89b4fa]/8 border-[#89b4fa]/20'
            : 'bg-[#313244]/20 border-[#313244]/40'
        }`}>
          <span className={`uppercase text-[10px] tracking-widest font-bold shrink-0 ${
            selectionMode ? 'text-[#89b4fa]' : 'text-gray-500'
          }`}>{modeLabel}:</span>
          <span className={`text-xs ${selectionMode ? 'text-[#89b4fa]/70' : 'text-[#6c7086]'}`}>{modeHint}</span>
        </div>

        {/* Canvas Container */}
        <div ref={containerRef} className="flex-1 overflow-hidden bg-[#0a0a14] mx-3 mb-3 mt-2 rounded-lg flex items-center justify-center relative">
          <TransformWrapper
            initialScale={1}
            minScale={0.5}
            maxScale={6}
            panning={{ disabled: selectionMode }}
            wheel={{ disabled: selectionMode }}
            pinch={{ disabled: selectionMode }}
            centerOnInit={true}
            onTransformed={(_, state) => setCurrentScale(state.scale)}
            onInit={(ref) => { transformRef.current = ref; }}
          >
            {({ zoomIn, zoomOut, resetTransform }) => (
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

                {/* Floating zoom pill */}
                <div className="absolute bottom-2.5 right-2.5 flex items-center gap-0.5 bg-[#11111b]/80 backdrop-blur-sm rounded-lg border border-[#313244]/50 px-1.5 py-1 z-10">
                  <button
                    onClick={() => zoomOut()}
                    className="w-7 h-7 flex items-center justify-center text-[#a6adc8] hover:text-[#cdd6f4] transition-colors"
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                  </button>
                  <span className="text-[#6c7086] text-xs w-11 text-center font-mono tabular-nums">
                    {Math.round(currentScale * 100)}%
                  </span>
                  <button
                    onClick={() => zoomIn()}
                    className="w-7 h-7 flex items-center justify-center text-[#a6adc8] hover:text-[#cdd6f4] transition-colors"
                  >
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
          <img ref={imageRef} src={testImagePath} onLoad={handleImageLoad} style={{ display: 'none' }} />
        </div>

        {/* Controls Panel — single row: Cancel | Page Nav (center) | Mode + Reset + Confirm */}
        <div className="border-t border-[#313244]/60 px-5 py-3 flex items-center gap-2">

          {/* Left: Cancel */}
          <button
            onClick={handleCancel}
            className={`${btn} border border-[#45475a] bg-[#181825] text-[#f38ba8] hover:bg-[#f38ba8]/10 hover:border-[#f38ba8]/40 active:bg-[#f38ba8]/20`}
          >
            Cancelar
          </button>

          <div className="flex-1" />

          {/* Center: Page Navigation */}
          <div className="flex items-center gap-1 shrink-0">
            <button disabled={currentPage === 1} className={btnIcon}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M7.5 2.5L4 6l3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            <div className="flex items-center bg-[#181825] border border-[#313244] rounded h-8 px-1.5 gap-0.5">
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
                className="w-6 bg-transparent text-[#cdd6f4] text-xs text-center font-mono outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
              <span className="text-[#585b70] text-xs font-mono">/</span>
              <span className="text-[#585b70] text-xs font-mono w-6 text-center">{totalPages}</span>
            </div>
            <button disabled={currentPage === totalPages} className={btnIcon}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2.5L8 6l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </div>

          <div className="flex-1" />

          {/* Right: MODO label + toggle | separator | Reset + Confirm */}
          <span className="uppercase text-[10px] tracking-widest text-gray-500 font-bold shrink-0">Modo</span>
          <button
            onClick={() => setSelectionMode(!selectionMode)}
            className={`${btn} w-28 ${
              selectionMode
                ? 'bg-[#89b4fa]/15 text-[#89b4fa] border border-[#89b4fa]/30 hover:bg-[#89b4fa]/20'
                : 'border border-[#313244] bg-[#181825] text-[#a6adc8] hover:bg-[#1e1e2e] hover:text-[#cdd6f4] hover:border-[#45475a]'
            }`}
          >
            {selectionMode ? 'Seleccionar' : 'Zoom / Pan'}
          </button>

          <div className="w-px h-5 bg-[#313244]/60" />

          <button onClick={handleReset} disabled={!selector} className={btnGhost}>
            Reset
          </button>

          <button
            onClick={handleConfirmClick}
            disabled={!selector}
            className={`${btn} bg-[#89b4fa] text-[#11111b] hover:bg-[#b4d0fb] active:bg-[#74a8f7] disabled:opacity-40 disabled:pointer-events-none`}
          >
            Confirmar
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]" style={{ backdropFilter: 'blur(2px)' }}>
          <div className="bg-[#1e1e2e] rounded-xl border border-[#313244] shadow-2xl w-72 flex flex-col overflow-hidden">
            <div className="px-4 pt-4 pb-3">
              <span className="uppercase tracking-widest text-xs text-gray-300 font-bold">Confirmar coordenadas</span>
            </div>
            {selector && (
              <div className="mx-4 bg-[#11111b] rounded-lg p-3 border border-[#313244]/50">
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
            <div className="flex gap-2 p-4">
              <button onClick={handleConfirmBack} className={`${btnGhost} flex-1`}>
                Volver
              </button>
              <button
                onClick={handleConfirmYes}
                className={`${btn} flex-1 bg-[#a6e3a1] text-[#11111b] hover:bg-[#b8eab3] active:bg-[#94d890]`}
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
