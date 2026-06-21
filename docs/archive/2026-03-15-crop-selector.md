# Crop Zone Selector — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (or superpowers:executing-plans) to implement. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone React component that lets users interactively select a rectangular zone on a PDF page by dragging, outputting 4 normalized coordinates.

**Architecture:** Canvas-based selector wrapped in a modal overlay. Uses `react-zoom-pan-pinch` for pan/zoom, Tailwind for UI consistency, real-time coordinate display for debugging.

**Tech Stack:** React 18, Canvas API, `react-zoom-pan-pinch` (already installed), Tailwind CSS

---

## File Structure

```
frontend/src/
├── components/
│   └── CropSelector.jsx          [NEW] Modal + canvas + controls
├── assets/
│   └── test-page.png             [NEW] 1024×1024 test image (or similar)
├── styles/
│   └── CropSelector.css          [NEW] Canvas-specific styles (if needed)
└── App.jsx                        [MODIFY] Add cropModal state + button
```

---

## Chunk 1: Canvas Component Foundation

### Task 1: Create CropSelector component scaffold

**Files:**
- Create: `frontend/src/components/CropSelector.jsx`

- [ ] **Step 1: Write component shell with state**

Create `frontend/src/components/CropSelector.jsx`:

```javascript
import { useState, useRef, useEffect } from 'react'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'

export default function CropSelector({ isOpen, onConfirm, onCancel, testImagePath }) {
  const canvasRef = useRef(null)
  const imageRef = useRef(null)

  // State: selector coordinates
  const [selector, setSelector] = useState({
    x_start: 0.25,
    x_end: 0.75,
    y_start: 0.10,
    y_end: 0.40,
  })

  // State: UI
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [zoomLevel, setZoomLevel] = useState(1)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [confirmed, setConfirmed] = useState(false)

  // Load test image on mount
  useEffect(() => {
    if (!testImagePath) return
    const img = new Image()
    img.onload = () => {
      imageRef.current = img
      drawCanvas()
    }
    img.src = testImagePath
  }, [testImagePath])

  // Draw canvas
  const drawCanvas = () => {
    const canvas = canvasRef.current
    if (!canvas || !imageRef.current) return

    const ctx = canvas.getContext('2d')
    const img = imageRef.current

    // Set canvas size to image size
    canvas.width = img.width
    canvas.height = img.height

    // Draw image
    ctx.drawImage(img, 0, 0)

    // Draw dark overlay
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
    ctx.fillRect(0, 0, img.width, img.height)

    // Draw clear rectangle (selected area)
    const x0 = selector.x_start * img.width
    const y0 = selector.y_start * img.height
    const x1 = selector.x_end * img.width
    const y1 = selector.y_end * img.height
    const w = x1 - x0
    const h = y1 - y0

    // Clear selected area (show image underneath)
    ctx.clearRect(x0, y0, w, h)

    // Draw border
    ctx.strokeStyle = '#89b4fa'
    ctx.lineWidth = 3
    ctx.strokeRect(x0, y0, w, h)
  }

  // Handle mouse events
  const handleCanvasMouseDown = (e) => {
    setIsDragging(true)
    const rect = canvasRef.current.getBoundingClientRect()
    setDragStart({
      x: (e.clientX - rect.left) / imageRef.current.width,
      y: (e.clientY - rect.top) / imageRef.current.height,
    })
  }

  const handleCanvasMouseMove = (e) => {
    if (!isDragging || !imageRef.current) return

    const rect = canvasRef.current.getBoundingClientRect()
    const currentX = (e.clientX - rect.left) / imageRef.current.width
    const currentY = (e.clientY - rect.top) / imageRef.current.height

    const x_start = Math.max(0, Math.min(dragStart.x, currentX))
    const x_end = Math.min(1, Math.max(dragStart.x, currentX))
    const y_start = Math.max(0, Math.min(dragStart.y, currentY))
    const y_end = Math.min(1, Math.max(dragStart.y, currentY))

    setSelector({ x_start, x_end, y_start, y_end })
    drawCanvas()
  }

  const handleCanvasMouseUp = () => {
    setIsDragging(false)
  }

  // Handle confirm
  const handleConfirm = () => {
    console.log('Crop coordinates captured:', selector)
    setConfirmed(true)
    if (onConfirm) onConfirm(selector)
  }

  // Handle reset
  const handleReset = () => {
    setSelector({
      x_start: 0.25,
      x_end: 0.75,
      y_start: 0.10,
      y_end: 0.40,
    })
    setConfirmed(false)
    drawCanvas()
  }

  // Handle cancel
  const handleCancel = () => {
    setConfirmed(false)
    if (onCancel) onCancel()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-surface/95 backdrop-blur-xl rounded-lg border border-white/10 shadow-2xl w-11/12 h-5/6 flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between bg-black/20">
          <h2 className="text-lg font-bold text-white">Seleccionar Zona de Escaneo</h2>
          <button
            onClick={handleCancel}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Canvas Container */}
        <div className="flex-1 overflow-hidden bg-black/30 relative">
          <TransformWrapper initialScale={1} minScale={0.5} maxScale={3}>
            <TransformComponent>
              <canvas
                ref={canvasRef}
                onMouseDown={handleCanvasMouseDown}
                onMouseMove={handleCanvasMouseMove}
                onMouseUp={handleCanvasMouseUp}
                onMouseLeave={handleCanvasMouseUp}
                className="cursor-crosshair"
                style={{ display: 'block' }}
              />
            </TransformComponent>
          </TransformWrapper>
        </div>

        {/* Controls Panel */}
        <div className="px-6 py-4 border-t border-white/5 bg-black/20 space-y-4">
          {/* Page Navigation */}
          <div className="flex items-center space-x-4 text-sm text-gray-300">
            <button
              className="bg-panel hover:bg-surface px-3 py-1.5 rounded border border-[#313244] transition-colors"
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage <= 1}
            >
              ← Anterior
            </button>
            <span className="font-mono">
              Página <input
                type="number"
                value={currentPage}
                onChange={(e) => setCurrentPage(Math.min(totalPages, Math.max(1, parseInt(e.target.value) || 1)))}
                className="w-12 px-2 py-1 bg-black/40 border border-white/10 rounded text-white text-center"
                min="1"
                max={totalPages}
              /> de {totalPages}
            </span>
            <button
              className="bg-panel hover:bg-surface px-3 py-1.5 rounded border border-[#313244] transition-colors"
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage >= totalPages}
            >
              Siguiente →
            </button>
          </div>

          {/* Coordinates Display */}
          <div className="bg-black/40 px-4 py-3 rounded font-mono text-sm text-gray-200 border border-white/5">
            <div className="grid grid-cols-4 gap-4">
              <div>
                <div className="text-gray-400 text-xs">x_start</div>
                <div className="font-bold text-accent">{selector.x_start.toFixed(3)}</div>
              </div>
              <div>
                <div className="text-gray-400 text-xs">x_end</div>
                <div className="font-bold text-accent">{selector.x_end.toFixed(3)}</div>
              </div>
              <div>
                <div className="text-gray-400 text-xs">y_start</div>
                <div className="font-bold text-accent">{selector.y_start.toFixed(3)}</div>
              </div>
              <div>
                <div className="text-gray-400 text-xs">y_end</div>
                <div className="font-bold text-accent">{selector.y_end.toFixed(3)}</div>
              </div>
            </div>
            {confirmed && (
              <div className="mt-2 text-green-400 text-xs font-bold">
                ✓ Coordenadas capturadas
              </div>
            )}
          </div>

          {/* Zoom Controls */}
          <div className="flex items-center space-x-2">
            <button
              className="bg-panel hover:bg-surface px-3 py-1.5 rounded border border-[#313244] transition-colors text-sm"
              onClick={() => setZoomLevel(Math.max(0.5, zoomLevel - 0.25))}
            >
              − Zoom
            </button>
            <span className="text-sm text-gray-400 w-12 text-center">{Math.round(zoomLevel * 100)}%</span>
            <button
              className="bg-panel hover:bg-surface px-3 py-1.5 rounded border border-[#313244] transition-colors text-sm"
              onClick={() => setZoomLevel(Math.min(3, zoomLevel + 0.25))}
            >
              + Zoom
            </button>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end space-x-3 pt-2">
            <button
              className="bg-panel hover:bg-surface px-4 py-2 rounded border border-[#313244] transition-colors text-gray-300 text-sm"
              onClick={handleReset}
            >
              Limpiar
            </button>
            <button
              className="bg-panel hover:bg-surface px-4 py-2 rounded border border-[#313244] transition-colors text-gray-300 text-sm"
              onClick={handleCancel}
            >
              Cancelar
            </button>
            <button
              className="bg-accent hover:bg-accent/80 px-4 py-2 rounded transition-colors text-black font-bold text-sm"
              onClick={handleConfirm}
            >
              Seleccionar
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify component exists and has no syntax errors**

Run: `cd frontend && npm run dev`
Expected: Dev server starts, no errors in console

---

### Task 2: Create test image asset

**Files:**
- Create: `frontend/src/assets/test-page.png`

- [ ] **Step 1: Create simple test image (1024×1024)**

Use ImageMagick or create placeholder programmatically. For now, create a simple 1024×1024 PNG with text "TEST PAGE" in center.

**Option A (ImageMagick):**
```bash
cd frontend/src/assets
convert -size 1024x1024 xc:white -pointsize 72 -fill black -gravity center -annotate +0+0 "TEST PAGE" test-page.png
```

**Option B (programmatic - create quick Node script):**
```javascript
// scripts/create-test-image.js
const fs = require('fs');
const canvas = require('canvas');

const c = canvas.createCanvas(1024, 1024);
const ctx = c.getContext('2d');

// White background
ctx.fillStyle = 'white';
ctx.fillRect(0, 0, 1024, 1024);

// Grid
ctx.strokeStyle = '#ccc';
ctx.lineWidth = 1;
for (let i = 0; i <= 1024; i += 128) {
  ctx.beginPath();
  ctx.moveTo(i, 0);
  ctx.lineTo(i, 1024);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(0, i);
  ctx.lineTo(1024, i);
  ctx.stroke();
}

// Text
ctx.fillStyle = 'black';
ctx.font = 'bold 72px Arial';
ctx.textAlign = 'center';
ctx.textBaseline = 'middle';
ctx.fillText('TEST PAGE', 512, 512);

// Line numbers (for debugging)
ctx.font = '14px monospace';
ctx.fillStyle = '#666';
for (let i = 0; i <= 1024; i += 128) {
  ctx.fillText(i, 20, i);
  ctx.fillText(i, i, 30);
}

const buffer = c.toBuffer('image/png');
fs.writeFileSync('frontend/src/assets/test-page.png', buffer);
```

For MVP simplicity: **use Option A (ImageMagick) if available, else manually create a white PNG with "TEST PAGE" text and save to `frontend/src/assets/test-page.png`**

- [ ] **Step 2: Verify image exists**

Run: `ls -lh frontend/src/assets/test-page.png`
Expected: File exists, size ~5-50KB

---

## Chunk 2: Integration & Testing

### Task 3: Integrate CropSelector into App.jsx

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Add import at top of App.jsx**

Find line ~1 (after other imports), add:

```javascript
import CropSelector from './components/CropSelector'
```

- [ ] **Step 2: Add crop modal state to App component**

Find the `useState` declarations (around line 4-35), add:

```javascript
const [showCropModal, setShowCropModal] = useState(false)
const [cropParams, setCropParams] = useState({
  x_start: 0.25,
  x_end: 0.75,
  y_start: 0.10,
  y_end: 0.40,
})
```

- [ ] **Step 3: Add button to open CropSelector in header**

Find the header section (around line 452-477, between "Historial" button and status indicator). Add:

```javascript
<button
  onClick={() => setShowCropModal(true)}
  className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]"
  title="Configurar zona de escaneo"
>
  <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 24 24">
    <rect x="4" y="4" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"/>
    <rect x="8" y="8" width="8" height="8" fill="currentColor" opacity="0.3"/>
  </svg>
  Zona de Escaneo
</button>
```

- [ ] **Step 4: Add CropSelector component before closing root div**

Find the closing `</div>` of the main container (at the very end of the return statement, around line ~900+). Before it, add:

```javascript
<CropSelector
  isOpen={showCropModal}
  onConfirm={(coords) => {
    setCropParams(coords)
    console.log('Crop params updated:', coords)
    setShowCropModal(false)
  }}
  onCancel={() => setShowCropModal(false)}
  testImagePath="/src/assets/test-page.png"
/>
```

- [ ] **Step 5: Verify App.jsx has no syntax errors**

Run: `cd frontend && npm run dev`
Expected: No console errors, button visible in header

---

### Task 4: Manual Testing in Browser

**Files:** None (testing only)

- [ ] **Step 1: Open browser and navigate to app**

```bash
# Terminal 1: Start frontend dev server
cd frontend && npm run dev

# Terminal 2: Open browser
# Navigate to http://localhost:5173
```

Expected: App loads, "Zona de Escaneo" button visible in header

- [ ] **Step 2: Click button to open CropSelector**

Click "Zona de Escaneo" button

Expected:
- Modal opens
- Test image visible with grid/text
- Coordinates panel shows initial values (0.250, 0.750, 0.100, 0.400)

- [ ] **Step 3: Test canvas interaction**

Drag on the canvas to select a new zone.

Expected:
- Rectangle appears and follows drag
- Coordinates update in real-time
- Dark overlay shows unselected area
- Selected area remains clear

- [ ] **Step 4: Test zoom controls**

Click "+ Zoom" and "− Zoom" buttons

Expected:
- Canvas size changes (zoom level % updates)
- Selector position stays in normalized coordinates

- [ ] **Step 5: Test page navigation**

Click "Siguiente →" button (should be disabled since totalPages=1)

Expected:
- Button disabled
- No crash

- [ ] **Step 6: Test manual page input**

Type "2" in page input field, press Enter

Expected:
- Updates to 2, then clamps back to 1 (since totalPages=1)

- [ ] **Step 7: Confirm selection**

Drag to set a selection, then click "Seleccionar"

Expected:
- "✓ Coordenadas capturadas" message appears in coordinate panel
- Browser console shows `Crop coordinates captured: { x_start: ..., x_end: ..., y_start: ..., y_end: ... }`
- Modal remains open (for reset)

- [ ] **Step 8: Test reset**

Click "Limpiar" button

Expected:
- Selection resets to default (0.25, 0.75, 0.10, 0.40)
- Confirmation message disappears
- Can select again

- [ ] **Step 9: Test cancel**

Click "Cancelar" button

Expected:
- Modal closes
- cropParams in App state unchanged (still has previous values)

- [ ] **Step 10: Verify App.jsx state integration**

Open browser DevTools → React tab, inspect `App` component state

Expected:
- `cropParams` shows current values after confirm
- `showCropModal` toggles correctly

---

### Task 5: Commit everything

**Files:**
- Created: `frontend/src/components/CropSelector.jsx`
- Created: `frontend/src/assets/test-page.png`
- Modified: `frontend/src/App.jsx`

- [ ] **Step 1: Check git status**

```bash
cd /a/PROJECTS/PDFoverseer
git status
```

Expected: New files + App.jsx listed as modified

- [ ] **Step 2: Stage files**

```bash
git add frontend/src/components/CropSelector.jsx \
        frontend/src/assets/test-page.png \
        frontend/src/App.jsx
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(frontend): crop zone selector MVP with canvas + real-time coordinates"
```

Expected: Commit succeeds, no pre-commit hooks fail

---

## Chunk 3: Polish & Documentation

### Task 6: Add inline code comments (if needed)

**Files:**
- Modify: `frontend/src/components/CropSelector.jsx` (optional, add comments if unclear)

- [ ] **Step 1: Review component for clarity**

Read through CropSelector.jsx and add JSDoc / inline comments to complex sections (canvas drawing, coordinate math, event handlers).

**Example:**
```javascript
// Normalize mouse position to 0.0-1.0 range
const currentX = (e.clientX - rect.left) / imageRef.current.width
```

- [ ] **Step 2: Commit if changes made**

```bash
git add frontend/src/components/CropSelector.jsx
git commit -m "docs(frontend): add CropSelector inline comments"
```

If no changes needed, skip this commit.

---

### Task 7: Verify styling matches existing app

**Files:**
- Verify: `frontend/src/App.jsx` (button styling)
- Verify: `frontend/src/components/CropSelector.jsx` (modal styling)

- [ ] **Step 1: Visual check in browser**

Open http://localhost:5173, click "Zona de Escaneo"

Expected:
- Button styling matches other buttons (bg-panel, border-[#313244], etc.)
- Modal uses same dark theme as app
- Text colors consistent (gray-300, white, accent)
- Tailwind classes all present (no fallback to raw CSS)

- [ ] **Step 2: Check for CSS file**

Verify no separate CSS file needed (Tailwind handles everything).

Expected:
- No `frontend/src/styles/CropSelector.css` created
- All styling via className + Tailwind

---

## Next Steps (Post-MVP)

1. **Backend integration:** Add `/api/crop_params` endpoint to save coordinates
2. **Multi-page support:** Replace static image with PDF.js rendering, loop through pages
3. **Persistence:** Store cropParams in localStorage or backend config
4. **App integration:** Show selector at first launch, re-accessible during analysis (paused state)
5. **Tests:** Add unit/integration tests if component becomes more complex

---

## Reference Files

- **Spec:** `docs/superpowers/specs/2026-03-15-crop-selector-design.md`
- **Component:** `frontend/src/components/CropSelector.jsx`
- **App integration:** `frontend/src/App.jsx`

