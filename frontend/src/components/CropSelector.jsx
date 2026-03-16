import { useState, useRef, useEffect } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';

export default function CropSelector({ isOpen, onConfirm, onCancel, testImagePath }) {
  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const [selector, setSelector] = useState({ x_start: 0.25, x_end: 0.75, y_start: 0.25, y_end: 0.75 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages] = useState(1);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [confirmed, setConfirmed] = useState(false);
  const [selectionMode, setSelectionMode] = useState(true);
  const [imageLoaded, setImageLoaded] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setConfirmed(false);
    }
  }, [isOpen]);

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

    const x_start = Math.max(0, Math.min(dragStart.x, x));
    const x_end = Math.max(0, Math.min(1, Math.max(dragStart.x, x)));
    const y_start = Math.max(0, Math.min(dragStart.y, y));
    const y_end = Math.max(0, Math.min(1, Math.max(dragStart.y, y)));

    setSelector({ x_start, x_end, y_start, y_end });
  };

  const handleCanvasMouseUp = () => {
    setIsDragging(false);
  };

  const handleConfirm = () => {
    console.log({ ...selector });
    setConfirmed(true);
    if (onConfirm) {
      onConfirm(selector);
    }
  };

  const handleReset = () => {
    setSelector({ x_start: 0.25, x_end: 0.75, y_start: 0.25, y_end: 0.75 });
    setConfirmed(false);
  };

  const handleImageLoad = () => {
    setImageLoaded(true);
  };

  const handleCancel = () => {
    if (onCancel) {
      onCancel();
    }
  };

  useEffect(() => {
    if (!imageLoaded || !canvasRef.current || !containerRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = imageRef.current;
    const container = containerRef.current;

    if (!img || !img.complete) return;

    // Calculate dimensions to fit container
    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;
    const imgAspect = img.naturalWidth / img.naturalHeight;
    const containerAspect = containerWidth / containerHeight;

    let displayWidth, displayHeight;
    if (imgAspect > containerAspect) {
      displayWidth = containerWidth;
      displayHeight = containerWidth / imgAspect;
    } else {
      displayHeight = containerHeight;
      displayWidth = containerHeight * imgAspect;
    }

    canvas.width = displayWidth;
    canvas.height = displayHeight;

    // Draw image
    ctx.drawImage(img, 0, 0, displayWidth, displayHeight);

    // Draw overlay (dark) - covers entire canvas
    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
    ctx.fillRect(0, 0, displayWidth, displayHeight);

    // Clear selected area to show image beneath
    const x = selector.x_start * displayWidth;
    const y = selector.y_start * displayHeight;
    const w = (selector.x_end - selector.x_start) * displayWidth;
    const h = (selector.y_end - selector.y_start) * displayHeight;

    ctx.clearRect(x, y, w, h);

    // Draw border around selection
    ctx.strokeStyle = '#89b4fa';
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);
  }, [isOpen, selector, imageLoaded]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-base rounded-lg shadow-xl w-11/12 h-5/6 flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center p-4 border-b border-[#313244]">
          <h2 className="text-xl font-bold text-gray-200">Seleccionar Zona de Escaneo</h2>
          <button
            onClick={handleCancel}
            className="text-gray-400 hover:text-gray-200 text-2xl"
          >
            ✕
          </button>
        </div>

        {/* Canvas Container */}
        <div ref={containerRef} className="flex-1 overflow-hidden bg-surface m-4 rounded-lg flex items-center justify-center">
          <TransformWrapper initialScale={1}>
            <TransformComponent>
              <canvas
                ref={canvasRef}
                onMouseDown={handleCanvasMouseDown}
                onMouseMove={handleCanvasMouseMove}
                onMouseUp={handleCanvasMouseUp}
                onMouseLeave={handleCanvasMouseUp}
                style={{
                  cursor: !selectionMode ? 'grab' : (confirmed ? 'default' : 'crosshair'),
                  touchAction: selectionMode ? 'none' : 'auto'
                }}
                className="border border-[#313244]"
              />
            </TransformComponent>
          </TransformWrapper>
          <img
            ref={imageRef}
            src={testImagePath}
            onLoad={handleImageLoad}
            style={{ display: 'none' }}
          />
        </div>

        {/* Controls Panel */}
        <div className="border-t border-[#313244] p-4 space-y-4">
          {/* Mode Toggle */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSelectionMode(!selectionMode)}
              className={`py-1.5 px-3 rounded border text-sm font-medium transition-colors ${
                selectionMode
                  ? 'bg-accent text-base border-accent'
                  : 'bg-panel hover:bg-surface text-gray-300 border-[#313244]'
              }`}
            >
              {selectionMode ? '✓ Modo Seleccionar' : 'Modo Pan/Zoom'}
            </button>
          </div>

          {/* Page Navigation */}
          <div className="flex items-center gap-3">
            <span className="text-gray-400 text-sm">Página {currentPage} de {totalPages}</span>
            <button
              disabled={currentPage === 1}
              className="bg-panel hover:bg-surface text-gray-300 py-1 px-3 rounded border border-[#313244] disabled:opacity-50 text-sm"
            >
              ← Anterior
            </button>
            <button
              disabled={currentPage === totalPages}
              className="bg-panel hover:bg-surface text-gray-300 py-1 px-3 rounded border border-[#313244] disabled:opacity-50 text-sm"
            >
              Siguiente →
            </button>
            <input
              type="number"
              min="1"
              max={totalPages}
              value={currentPage}
              onChange={(e) => setCurrentPage(Math.min(totalPages, Math.max(1, parseInt(e.target.value) || 1)))}
              className="bg-panel border border-[#313244] text-gray-300 py-1 px-2 rounded w-16 text-sm"
            />
          </div>

          {/* Zoom Controls */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setZoomLevel(Math.max(50, zoomLevel - 25))}
              className="bg-panel hover:bg-surface text-gray-300 py-1 px-3 rounded border border-[#313244] text-sm"
            >
              Alejar −
            </button>
            <span className="text-gray-400 text-sm w-16 text-center">{zoomLevel}%</span>
            <button
              onClick={() => setZoomLevel(Math.min(200, zoomLevel + 25))}
              className="bg-panel hover:bg-surface text-gray-300 py-1 px-3 rounded border border-[#313244] text-sm"
            >
              Acercar +
            </button>
          </div>

          {/* Coordinate Display */}
          <div className="bg-surface p-3 rounded border border-[#313244]">
            <div className="text-xs text-gray-400 space-y-1 font-mono">
              <div>x_start: {selector.x_start.toFixed(3)} | x_end: {selector.x_end.toFixed(3)}</div>
              <div>y_start: {selector.y_start.toFixed(3)} | y_end: {selector.y_end.toFixed(3)}</div>
            </div>
          </div>

          {confirmed && (
            <div className="bg-green-900/30 border border-green-700 text-green-300 p-2 rounded text-sm">
              ✓ Coordenadas capturadas: {JSON.stringify(selector)}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              className="bg-panel hover:bg-surface text-gray-300 py-2 px-4 rounded border border-[#313244] text-sm flex-1"
            >
              Limpiar
            </button>
            <button
              onClick={handleConfirm}
              className="bg-accent hover:bg-blue-500 text-base py-2 px-4 rounded text-sm flex-1 font-medium"
            >
              Seleccionar
            </button>
            <button
              onClick={handleCancel}
              className="bg-panel hover:bg-surface text-gray-300 py-2 px-4 rounded border border-[#313244] text-sm flex-1"
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
