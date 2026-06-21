# Crop Zone Selector — MVP Design Spec

**Date:** 2026-03-15
**Status:** Design Review
**Scope:** Standalone React component for interactive PDF zone selection (no backend integration in MVP)

---

## Overview

Interactive UI component that allows users to select a rectangular zone from a PDF page by dragging the mouse. The selected zone is defined by 4 normalized coordinates (`x_start`, `x_end`, `y_start`, `y_end`, each 0.0–1.0) that feed the crop pipeline in future backend integration.

**MVP Constraints:**
- Standalone component (no backend integration)
- Static test image (no real PDF rendering yet)
- Canvas-based selector with real-time coordinate display
- Modal overlay architecture (consistent with existing app UI)

---

## Requirements

### Functional Requirements

1. **Visual PDF Viewer**
   - Display static test image for a full size A4 with a grid
   - Support pan/zoom via `react-zoom-pan-pinch` (already installed)
   - Render at 150 DPI equivalent (or visual equivalent)

2. **Interactive Selector**
   - User drags mouse to draw rectangular selection
   - Visual feedback: rectangle with solid border, 50% opacity external fill
   - Fill color strategy: rest of page darkens (50% opaque overlay), selected area remains clear
   - Selector follows pan/zoom transformations

3. **Page Navigation**
   - Display "Page X of Y" counter
   - Previous/Next buttons (disabled at boundaries)
   - Manual page input: user types page number, jumps directly
   - (MVP: single page, future-proof for multi-page)

4. **Controls**
   - Zoom in/out buttons (±25% increments)
   - "Seleccionar" (Confirm) button → finalizes selection
   - "Cancelar" (Cancel) button → closes modal without saving, put a placeholder for now
   - Reset button: clears current selection

5. **Real-Time Coordinate Display**
   - Shows live coordinates as user drags:
     ```
     x_start: 0.25 | x_end: 0.75
     y_start: 0.10 | y_end: 0.40
     ```
   - Updates every mousemove
   - Freezes on button confirm

6. **Confirmation Feedback**
   - Console log: `console.log({ x_start, x_end, y_start, y_end })`
   - UI message: "✓ Coordenadas capturadas"
   - JSON display of final values (debugging)
   - Callback/event emitted for parent to consume

---

## Architecture

### Component Structure

```
<CropSelector>
  ├── Modal overlay (Tailwind styled)
  │   ├── Header (title + close)
  │   ├── Canvas container
  │   │   └── <TransformWrapper> (react-zoom-pan-pinch)
  │   │       └── <Canvas> (selector drawing)
  │   ├── Controls panel (Tailwind)
  │   │   ├── Page navigation (input + buttons)
  │   │   ├── Zoom controls
  │   │   ├── Coordinate display (real-time)
  │   │   └── Action buttons (Select/Cancel/Reset)
```

### Data Flow

```
User mouse event (mousedown/mousemove/mouseup)
  → Update selector state { x_start, x_end, y_start, y_end }
  → Re-render canvas + coordinate display

User clicks "Seleccionar"
  → Finalize coordinates
  → Emit onConfirm callback with { x_start, x_end, y_start, y_end }
  → Console log for debugging
  → Display confirmation message
  → Close modal (or stay open for reset)
```

---

## Technical Details

### Canvas Rendering

- **Canvas size:** Match transformed image dimensions (via `react-zoom-pan-pinch`)
- **Image layer:** Draw static test image
- **Overlay layer:** Dark semi-transparent rect covering entire page
- **Selector layer:** Clear rectangle (inverse mask) showing selected zone
- **Border layer:** Solid lines around selector (2–3px, accent color)

### Coordinate System

- **Input:** raw pixel coordinates from mouse events
- **Normalized output:** `x/imageWidth`, `y/imageHeight` (0.0–1.0 range)
- **Validation:** Ensure `x_start < x_end` and `y_start < y_end`; clamp to [0, 1]

### Styling

**Consistency with existing app:**
- Dark theme (Tailwind: `bg-base`, `bg-surface`, `text-gray-200`)
- Button styles: `bg-panel hover:bg-surface` with `border-[#313244]`
- Accent color: `bg-accent` for confirm button
- Modal backdrop: `fixed inset-0 bg-black/50`

**Selector visual:**
- Border: solid 2px, color `#89b4fa` (accent)
- Fill: `rgba(137, 180, 250, 0.5)` (50% opacity)
- Rest of page: `rgba(0, 0, 0, 0.6)` overlay

---

## State Management

**Local component state:**
```javascript
{
  x_start: number,      // 0.0–1.0
  x_end: number,        // 0.0–1.0
  y_start: number,      // 0.0–1.0
  y_end: number,        // 0.0–1.0
  currentPage: number,
  totalPages: number,
  zoomLevel: number,    // percentage or multiplier
  isDragging: boolean,
  dragStart: { x, y }   // for computing delta
}
```

**Parent component integration (future):**
- Prop: `isOpen: boolean`
- Prop: `onConfirm: (coords) => void`
- Prop: `onCancel: () => void`
- Prop: `testImagePath: string` (MVP)

---

## Testing & Validation (MVP)

1. **Visual:** Selector rectangle appears and follows drag correctly
2. **Coordinates:** Display updates in real-time; values clamp to [0, 1]
3. **Confirm:** Console log shows correct final values
4. **Pan/Zoom:** Selector position updates when zooming/panning
5. **Navigation:** Page counter updates; buttons disabled at boundaries
6. **Styling:** Consistent with existing app (dark theme, Tailwind)

---

## Future Integration (Post-MVP)

1. **Backend params:** Send coordinates to `/api/crop_params` endpoint
2. **Real PDF:** Replace static image with PDF.js rendering
3. **Multi-page:** Loop through PDF pages in selector
4. **Persistence:** Store in `localStorage` or backend config
5. **App integration:** Appear at onboarding + mid-analysis (paused state)

---

## Worktree & Branch

**Branch:** `feature/crop-selector`
**Worktree location:** `.worktrees/crop-selector/`
**Isolation:** No changes to main pipeline; frontend-only

---

## Open Questions / Decisions

- **Test image:** Use placeholder PNG or real PDF page screenshot?
- **Modal stay open after confirm?** (for multiple selections / reset)
- **Color scheme:** Finalize accent color for selector + button states
- **Mouse cursor:** Change to crosshair during selection?

