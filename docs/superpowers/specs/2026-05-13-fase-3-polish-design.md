# PDFoverseer FASE 3 — Polish pass: design system, primitives, density

**Fecha:** 2026-05-13
**Rama:** `po_overhaul` (continúa después de tag `fase-2-mvp` + commit `384004b` `fix(fase2): folder_path + home total cascade`)
**Spec FASE 2:** `docs/superpowers/specs/2026-05-12-fase-2-design.md`
**Research backing:**
- `docs/research/2026-05-13-frontend-audit.md` (code audit, design system proposal)
- `docs/research/2026-05-13-frontend-references.md` (industry pattern research)

---

## 1. Goal

Transformar la UI actual de FASE 2 — funcionalmente completa pero visualmente sin sistema, percibida por el product owner como "como algo entregado por un junior" — en una superficie operativa, densa y profesional al nivel de Linear / Mercury / Vercel Dashboard. No hay cambios funcionales: cada interacción de FASE 2 (scan, OCR per cell, override, lightbox, Excel) se preserva. Lo que cambia es **el sistema visual, los primitivos compartidos, el lenguaje, y la densidad**.

## 2. Scope

**Incluye:**

- Token system semántico en `tailwind.config.js` apoyado en Radix Colors dark scales
- Adopción de 4 librerías nuevas (`lucide-react`, `@radix-ui/colors`, `@radix-ui/react-{dialog,tooltip,popover}`, `sonner`, `windy-radix-palette`)
- 7 primitivos compartidos bajo `frontend/src/ui/`
- Rediseño de los 10 componentes activos preservando comportamiento
- Agrupamiento de `CategoryRow` en 2 secciones colapsables (Normalizadas / Compilaciones) basado en el flag `compilation_suspect`
- Inline-edit en la celda de count (patrón Retool)
- `<SaveIndicator/>` en `OverridePanel` (autosave visible)
- Reemplazo del wrapping del `PDFLightbox` por `@radix-ui/react-dialog` (focus trap + a11y)
- Sistema de toasts vía `sonner` reemplazando `alert()`
- Microcopy completo en castellano sin jargon ingenieril
- Borrado de 4 componentes muertos (`HeaderBar`, `Sidebar`, `ProgressBar`, `ScanIndicator`) + README stale + exports muertos en `constants.js`
- Ribbon de 18 dots en `HospitalCard` para telemetría de un vistazo
- Empty state accionable para HLL (`Sin carpeta normalizada` + CTA)

**Out of scope (deferred a FASE 4):**

- Refinamiento per-sigla de motores OCR (header_detect template-sharing, corner_count ART gap, charla compilation-vs-N-PDFs)
- Page-level cancellation (objetivo <3s vs ~30s actual)
- Auto-retry on OCR failure
- Multi-month overview / cross-month comparison
- Mostrar docs encontrados por archivo en panel Archivos (requiere cambio de schema en `ScanResult`)
- Light mode, responsive mobile, keyboard shortcuts
- Animaciones decorativas / microinteractions de delight
- Tema customizable, theming, fonts on-demand
- Settings UI

## 3. Mental model (la dimensión que la UI actual no expresa)

Memoria `project_pdfoverseer_purpose` documenta el modelo central: **dos regímenes de conteo**.

- **Régimen 1 — Normalizado** (~90% de celdas): un PDF por documento, nombrado predeciblemente. `filename_glob` da el conteo final en milisegundos. Confidence HIGH excepto si hay `some_files_unrecognized`.
- **Régimen 2 — Compilación** (~10%): un PDF gigante contiene N documentos encuadernados. `filename_glob` da 1 (un solo archivo) pero la heurística `flag_compilation_suspect` levanta el flag. Requiere OCR (header_detect, corner_count, page_count_pure) para encontrar boundaries de documento.

La UI actual mezcla las 18 siglas en una lista plana. Eso esconde el modelo. La UI de FASE 3 separa físicamente los dos regímenes en 2 secciones, con la sección "Compilaciones" presentando la acción "Escanear todas" en su header (en vez de un botón global ambiguo "OCR suspects de HPV").

## 4. Design system

### 4.1 Color tokens (Radix Colors → semantic)

Adoptar `@radix-ui/colors` para tener una escala de 12 pasos con propósito documentado por step. **No usar `windy-radix-palette`** — su versión 2.x no documenta compat con Tailwind 3 y es redundante con la estrategia de importar las variables CSS directamente (este enfoque también es más liviano: cero plugins). Mecánica:

1. En `frontend/src/index.css` agregar (top of file, antes de `@tailwind`):

```css
@import "@radix-ui/colors/slate-dark.css";
@import "@radix-ui/colors/indigo-dark.css";
@import "@radix-ui/colors/jade-dark.css";
@import "@radix-ui/colors/amber-dark.css";
@import "@radix-ui/colors/ruby-dark.css";
@import "@radix-ui/colors/iris-dark.css";
```

Esto expone variables CSS `--slate-1`...`--slate-12`, `--indigo-1`...`--indigo-12`, etc. (sin sufijo `Dark` — el sufijo está en el nombre del archivo CSS importado).

2. En `tailwind.config.js` definir tokens **semánticos** referenciando esas variables:

```js
// tailwind.config.js — theme.extend.colors
{
  'po-bg':              'var(--slate-1)',
  'po-panel':           'var(--slate-2)',
  'po-panel-hover':     'var(--slate-3)',
  'po-border':          'var(--slate-6)',
  'po-border-strong':   'var(--slate-7)',
  'po-text':            'var(--slate-12)',
  'po-text-muted':      'var(--slate-11)',
  'po-text-subtle':     'var(--slate-10)',

  'po-confidence-high': 'var(--jade-11)',
  'po-confidence-low':  'var(--amber-11)',

  'po-suspect':         'var(--amber-9)',
  'po-suspect-bg':      'var(--amber-3)',
  'po-error':           'var(--ruby-11)',
  'po-error-bg':        'var(--ruby-3)',
  'po-scanning':        'var(--indigo-10)',
  'po-override':        'var(--iris-11)',
  'po-override-bg':     'var(--iris-3)',
  'po-success':         'var(--jade-11)',

  'po-accent':          'var(--indigo-9)',
  'po-accent-hover':    'var(--indigo-10)',
}
```

Implementer puede leer los hex exactos en cada Radix scale doc (`https://www.radix-ui.com/colors/docs/palette-composition/scales`) si necesita pegar valores en mockups.

**Regla:** ninguna clase Tailwind `bg-slate-*`, `bg-indigo-*`, `bg-emerald-*`, `border-slate-*`, `text-slate-*` directa en JSX nuevo o migrado. Todo color pasa por un token `po-*`. Verificación al cierre (ver §7 AC9).

### 4.2 Tipografía

- `font-sans` default: `Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif` (cargar Inter via `@fontsource/inter`, no Google Fonts)
- `font-mono` para sigla, filenames, timestamps, OCR debug: `JetBrains Mono, ui-monospace, "Cascadia Code", monospace` (`@fontsource/jetbrains-mono`)
- Escala fija:

  | Token | Tailwind class | Uso |
  |-------|----------------|-----|
  | `display` | `text-4xl font-semibold tracking-tight tabular-nums` | Big count en HospitalCard, Detalle |
  | `title` | `text-xl font-semibold` | Page titles (HPV, "Hospitales") |
  | `subtitle` | `text-xs font-medium uppercase tracking-wider text-po-text-muted` | Section labels (CATEGORÍAS, DETALLE, ARCHIVOS) |
  | `body` | `text-sm text-po-text` | Default |
  | `meta` | `text-xs text-po-text-muted` | Footnotes, "{n} de {m}" |
  | `mono` | `font-mono text-xs text-po-text` | Sigla, filenames, timestamps |

- **Numerales siempre `tabular-nums`** en cualquier celda de count, tabla, ribbon, breakdown.
- Line height base `1.45` (más apretado que Tailwind default `leading-normal` 1.5).

### 4.3 Spacing & density

- Tailwind defaults sin custom values. Todo alinea a 4/8/12/16/24px.
- `CategoryRow`: 32px height (`py-2` en row container). Equivalente a "Short" de Airtable.
- Row padding horizontal `px-3`.
- Section gap entre Categorías / Detalle / Archivos: `gap-6`.
- Card padding: `p-5` en `HospitalCard`, `p-4` en panels internos.

### 4.4 Iconography — `lucide-react`

Decisión: `lucide-react@^0.400.0`. `strokeWidth={1.75}`, tamaños:

- **16px**: inline-with-text (en pills, breadcrumbs, file rows)
- **20px**: buttons, action triggers
- **24px**: empty state hero icons

Mapeo definitivo de placeholders actuales:

| Hoy (placeholder) | Ubicación | Reemplazar con |
|-------------------|-----------|----------------|
| `⟳` scanning pulse | `CategoryRow.jsx:37` | `<Loader2 className="animate-spin" />` |
| `✕` error | `CategoryRow.jsx:38`, `PDFLightbox close` | `<AlertCircle />` (estado), `<X />` (cerrar) |
| `⚠` compilation_suspect | `CategoryRow.jsx:39`, `FileList:63` | `<FileStack />` |
| `←` back | `HospitalDetail.jsx:54` | `<ArrowLeft />` |
| (none) Escanear todo | `MonthOverview.jsx:60` | `<RefreshCw />` |
| (none) Generar Resumen | `MonthOverview.jsx:70` | `<FileSpreadsheet />` |
| (none) Override active | new | `<PenLine />` |
| (none) Hospital tile | `HospitalCard` | `<Building2 />` |
| (none) Empty file list | `FileList` empty | `<FileX />` |
| (none) Empty folder (HLL) | `HospitalCard` HLL | `<FolderX />` |
| (none) Scan trigger | various | `<Scan />` |
| (none) Done/success | toast / state | `<CheckCircle2 />` |
| (none) Save spinner | `SaveIndicator` | `<Loader2 className="animate-spin" />` |

### 4.5 UI primitives (`frontend/src/ui/`)

Tres niveles de primitivo:

**Hand-rolled (sin deps):**

1. **`Button.jsx`** — primitivo central. API:

   ```jsx
   <Button
     variant="primary" | "secondary" | "ghost" | "destructive"
     size="sm" | "md"
     icon={LucideComponent}    // optional, renders 16px before label
     disabled
     onClick
   >Label</Button>
   ```

   Base classes (siempre): `inline-flex items-center gap-1.5 rounded-md font-medium transition disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-po-accent`.

   Por size:
   - `sm`: `text-xs px-2.5 py-1`
   - `md`: `text-sm px-3 py-1.5`

   Por variant:
   - `primary`: `bg-po-accent text-white hover:bg-po-accent-hover`
   - `secondary`: `bg-po-panel border border-po-border hover:border-po-border-strong text-po-text`
   - `ghost`: `text-po-text-muted hover:text-po-text hover:bg-po-panel-hover`
   - `destructive`: `border border-po-error text-po-error hover:bg-po-error-bg`

   Default size si no se pasa: `md`. Default variant: `secondary`. Icon size always 16 with `strokeWidth={1.75}`.

2. **`Badge.jsx`** — `<Badge variant="confidence-high" icon={CheckCircle2}>Alta</Badge>`. Variants: `confidence-high`, `confidence-low`, `state-suspect`, `state-scanning`, `state-error`, `state-override`, `neutral`. Forma: `rounded-full px-2 py-0.5 text-[11px] font-medium inline-flex items-center gap-1 border`.

3. **`Dot.jsx`** — `<Dot variant="confidence-high" />`. 8×8 `rounded-full` solid color. Used in CategoryRow + HospitalCard ribbon.

4. **`SaveIndicator.jsx`** — controlled prop `status: 'idle' | 'saving' | 'saved' | 'error'`. Idle: nothing rendered. Saving: `<Loader2 size={12} className="animate-spin" /> Guardando…` en `text-po-text-muted`. Saved: `<CheckCircle2 size={12} className="text-po-success" /> Guardado` fades after 2s. Error: `<AlertCircle size={12} className="text-po-error" /> No se pudo guardar`.

5. **`EmptyState.jsx`** — `<EmptyState icon={FileX} title="..." description="..." action={<Button>...</Button>} />`. Geist recipe.

6. **`Skeleton.jsx`** — `<Skeleton className="h-4 w-12" />`. `bg-po-panel-hover animate-pulse rounded`.

**Radix-wrapped (a11y critical):**

7. **`Tooltip.jsx`** — wraps `@radix-ui/react-tooltip`. API: `<Tooltip content="...">{trigger}</Tooltip>`. Provider sits at App level with `delayDuration={300}`.

8. **`Dialog.jsx`** — wraps `@radix-ui/react-dialog`. API: `<Dialog open={...} onOpenChange={...}><Dialog.Header>...</Dialog.Header><Dialog.Body>...</Dialog.Body></Dialog>`. Used by PDFLightbox.

**Toast (external):**

`sonner`'s `<Toaster />` global en `App.jsx`. Llamar `toast.success("Excel guardado en {path}")`, `toast.error("OCR falló para HPV/odi")`. Posición `bottom-right`.

### 4.6 Microcopy

Tabla normativa en castellano. **El implementer NO improvisa traducciones — esta tabla es la fuente.**

| Hoy | Mañana |
|-----|--------|
| `compilation_suspect` (flag raw) en JSX | Badge: `Compilación` / Tooltip: `Probable compilación (PDF con >5× páginas esperadas)` |
| `via filename_glob` | `Método: Nombre` (mapping: `filename_glob`→`Nombre`, `header_detect`→`Encabezados OCR`, `corner_count`→`Recuadro de página`, `page_count_pure`→`Conteo de páginas`, `manual`→`Manual`) |
| `no normalizado` (HLL) | Título `Sin carpeta normalizada` + body `HLL no entrega PDFs por carpeta este mes. Ingresa los conteos a mano.` + CTA `Ingresar conteos` |
| `OCR 0 seleccionadas` (disabled) | `Selecciona categorías para OCR` |
| `OCR N seleccionadas` (active) | `Escanear {n} categoría` / `Escanear {n} categorías` (pluralizado) |
| `OCR suspects de HPV` | Mover al header de sección Compilaciones: `Escanear todas` (n=count de compilaciones en sección) |
| `Confidence: low` (texto) | Badge `Baja` (rojo) / `Alta` (verde) |
| `Filename:` / `OCR:` | `Por nombre de archivo` / `Por OCR` |
| `Sigla:` (label) | (eliminado — la sigla ES el título del panel Detalle) |
| `Flags: compilation_suspect` (row) | (eliminado — flags renderean como pills bajo el número) |
| `Escanear todo` (botón) | `Escanear todos los hospitales` |
| `Generar Resumen` | `Generar Excel del mes` |
| `alert("Generado: {path}")` | `toast.success("Excel guardado en {path}")` con icono `FileSpreadsheet` |
| Subtitle `FASE 2` (App header) | (eliminado) |
| `Cargando…` | `<Skeleton/>` con dimensiones aproximadas al contenido final |
| `Sin PDFs` | `<EmptyState icon={FileX} title="Sin archivos" description="Esta categoría no tiene archivos PDF en este mes." />` |
| `Cancel` (ScanProgress) | `Cancelar` con estilo destructive (`border-po-error text-po-error`) |
| `Completado · 18/18` | `Completado` + badge con count, auto-dismiss a 5s |
| `Buscar...` (FileList search) | `Buscar archivo…` |
| `Override:` (OverridePanel) | `Ajuste manual` (heading h3) |
| `Nota:` (OverridePanel) | `Nota (opcional)` |

## 5. Component specifications

Cada sección describe el resultado final (forma + comportamiento). Comportamiento preexistente de FASE 2 se preserva salvo donde explícitamente se indica.

### 5.1 `App.jsx`

```jsx
<TooltipProvider delayDuration={300}>
  <div className="min-h-screen bg-po-bg text-po-text font-sans">
    <header className="border-b border-po-border px-6 py-4">
      <h1 className="text-lg font-semibold">PDFoverseer</h1>
      {/* "FASE 2" subtitle removed */}
    </header>
    <main className="px-6 py-6 max-w-[1600px] mx-auto">
      {view === "month" ? <MonthOverview /> : <HospitalDetail .../>}
    </main>
    <PDFLightbox />
    <ScanProgress />
    <Toaster position="bottom-right" theme="dark" />
  </div>
</TooltipProvider>
```

### 5.2 `MonthOverview.jsx`

- Month picker: row de botones con icon `<Calendar size={14} />` + label `ABRIL 2026`. Selected: `bg-po-accent text-white`. Resting: `bg-po-panel border border-po-border hover:border-po-border-strong`.
- Action buttons: dos botones lado a lado, separados por divider. `<Button primary icon={RefreshCw}>Escanear todos los hospitales</Button>` `<Button icon={FileSpreadsheet}>Generar Excel del mes</Button>` (segundo es solid emerald — su jerarquía: el primary del primer paso es el indigo; al completar scan, el primary cambia a "Generar").
- Reemplazar `alert()` por `toast.success("Excel guardado en {result.output_path}")`.
- Hospital grid: 4 columns at `xl:`, 2 columns below 1280px.

### 5.3 `HospitalCard.jsx`

Estado "presente" (HPV, HRB, HLU normalmente):

```jsx
<button className="rounded-xl bg-po-panel border border-po-border p-5 hover:border-po-border-strong transition text-left">
  <div className="flex items-center justify-between mb-3">
    <div className="flex items-center gap-2 text-po-text-muted">
      <Building2 size={14} />
      <span className="text-sm font-medium text-po-text">{hospital}</span>
    </div>
    <span className="text-xs text-po-text-muted">{relativeTime(scannedAt)}</span>
  </div>
  <p className="text-4xl font-semibold tabular-nums">{total.toLocaleString()}</p>
  <p className="text-xs text-po-text-muted mt-0.5">documentos detectados</p>
  <div className="flex gap-0.5 mt-4">
    {SIGLAS.map(s => <Dot key={s} variant={confidenceOf(cells[s])} />)}
  </div>
</button>
```

Donde `confidenceOf(cell)` retorna `'confidence-high' | 'confidence-low' | 'state-error' | 'neutral'` según el estado del cell.

Estado "no normalizado" (HLL):

```jsx
<div className="rounded-xl bg-po-panel border border-po-border p-5">
  <div className="flex items-center gap-2 text-po-text-muted mb-3">
    <Building2 size={14} />
    <span className="text-sm font-medium text-po-text">{hospital}</span>
  </div>
  <EmptyState
    icon={FolderX}
    title="Sin carpeta normalizada"
    description={`${hospital} no entrega PDFs por carpeta este mes. Ingresa los conteos a mano.`}
    action={<Button onClick={openManualEntry}>Ingresar conteos</Button>}
  />
</div>
```

(El flow "Ingresar conteos" puede ser un panel que reuse `OverridePanel` por sigla — implementer decide vs deferir si la complejidad excede el polish pass.)

### 5.4 `HospitalDetail.jsx`

Header:

```jsx
<header className="flex items-center gap-4 mb-6">
  <button onClick={onBack} className="text-po-text-muted hover:text-po-text inline-flex items-center gap-1 text-sm">
    <ArrowLeft size={16} /> Volver
  </button>
  <h2 className="text-xl font-semibold">{hospital}</h2>
  <span className="text-sm text-po-text-muted">Total: <span className="tabular-nums">{total.toLocaleString()}</span></span>
  <div className="ml-auto">
    <ScanControls hospital={hospital} selectedSiglas={[...selectedSet]} />
  </div>
</header>
```

Layout: 3 columns at `xl:`, stacked below. `gap-6`.

```jsx
<div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-6">
  <CategoriesSection ... />   {/* §5.5 */}
  <DetailSection ... />        {/* §5.6 */}
  <FilesSection ... />         {/* §5.7 */}
</div>
```

### 5.5 Categories section (rediseño grande)

**Estructura: 2 secciones colapsables.** Partition por `cell.flags.includes("compilation_suspect")`:

```jsx
<section>
  <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">CATEGORÍAS</h3>
  <CategoryGroup title="Normalizadas" cells={normalCells} defaultOpen={true} />
  <CategoryGroup
    title="Compilaciones"
    cells={suspectCells}
    defaultOpen={true}
    headerAction={
      <Button size="sm" icon={Scan} onClick={() => scanAllSuspectsFor(hospital)}>
        Escanear todas
      </Button>
    }
  />
</section>
```

`CategoryGroup`:

```jsx
<div className="border-b border-po-border last:border-b-0">
  <div className="flex items-center justify-between py-2">
    <button className="inline-flex items-center gap-2 text-sm font-medium" onClick={toggle}>
      {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      {title} <span className="text-po-text-muted">· {cells.length}</span>
    </button>
    {headerAction}
  </div>
  {open && (
    <div>
      {cells.map(cell => <CategoryRow key={cell.sigla} cell={cell} ... />)}
    </div>
  )}
</div>
```

**`CategoryRow` (single-line 32px):**

```jsx
<div className={cn(
  "flex items-center gap-3 px-3 h-8 hover:bg-po-panel-hover transition",
  selected && "bg-po-panel-hover border-l-2 border-po-accent",
)}>
  <input type="checkbox" checked={checked} onChange={...} className="..."/>
  <Tooltip content={SIGLA_LABELS[sigla]}>
    <button onClick={() => onSelect(sigla)} className="font-mono text-xs text-po-text">
      {sigla}
    </button>
  </Tooltip>
  <Dot variant={confidenceVariant(cell)} className="ml-1" />

  <div className="ml-auto flex items-center gap-2">
    {isScanning ? (
      <Badge variant="state-scanning" icon={Loader2}>Escaneando…</Badge>
    ) : (
      <>
        {isCompilationSuspect && (
          <Tooltip content="Probable compilación (PDF con >5× páginas esperadas)">
            <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
          </Tooltip>
        )}
        {hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
        {hasError && <Badge variant="state-error" icon={AlertCircle}>Error</Badge>}
        <InlineEditCount value={count} onCommit={v => saveOverride(hospital, sigla, v)} />
      </>
    )}
  </div>
</div>
```

`InlineEditCount`:

```jsx
function InlineEditCount({ value, onCommit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  if (!editing) {
    return (
      <button
        onClick={() => { setDraft(value); setEditing(true); }}
        className="font-mono tabular-nums text-sm w-14 text-right hover:text-po-accent"
      >
        {value?.toLocaleString() ?? "—"}
      </button>
    );
  }
  return (
    <input
      type="number"
      autoFocus
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onKeyDown={e => {
        if (e.key === "Enter") { onCommit(parseInt(draft)); setEditing(false); }
        if (e.key === "Escape") { setEditing(false); }
      }}
      onBlur={() => setEditing(false)}
      className="font-mono tabular-nums text-sm w-14 text-right bg-po-panel border border-po-accent rounded px-1"
    />
  );
}
```

**Comportamiento clave:** Enter dispara save → toast notification opcional; Escape descarta. Indicador visual de "edited but not saved" via dot pulsante hasta que el WS confirme.

**Constante nueva:** `frontend/src/lib/sigla-labels.js`. **Fuente de verdad: `core/domain.py:CATEGORY_FOLDERS`** — usar los nombres de carpeta limpios (sin prefijo numérico, normalizados con tildes y minúsculas-iniciales). NO inventar significados expandidos.

```js
// Derived from core/domain.py CATEGORY_FOLDERS (prefix N.- stripped, tildes added).
// If a label reads awkwardly in tooltips, the implementer MUST confirm with
// Daniel before changing it. NEVER fabricate domain meaning — the folder name
// IS the domain label.
export const SIGLA_LABELS = {
  reunion: "Reunión de prevención",
  irl: "Inducción IRL",
  odi: "ODI Visitas",
  charla: "Charlas",
  chintegral: "Charla integral",
  dif_pts: "Difusión PTS",
  art: "ART",
  insgral: "Inspecciones generales",
  bodega: "Inspección bodega",
  maquinaria: "Inspección de maquinaria",
  ext: "Extintores",
  senal: "Señaléticas",
  exc: "Excavaciones y vanos",
  altura: "Trabajos en altura",
  caliente: "Inspección trabajos en caliente",
  herramientas_elec: "Inspección herramientas eléctricas",
  andamios: "Andamios",
  chps: "CHPS",
};
```

Las siglas que son ya acrónimos canónicos (ART, ODI, IRL, PTS, CHPS) **NO se expanden** en este label — Daniel los usa como acrónimos. La expansión completa, si existiera, va en el tooltip o en un futuro glosario. Implementer: si una de estas etiquetas no aparece bien en el panel Detalle (porque la sigla ya es muy descriptiva, p.ej. `senal: "Señaléticas"` rinde redundante), considerar omitir el separador `·` y la etiqueta cuando label.toLowerCase() === sigla.toLowerCase().

### 5.6 Detail section (panel central)

Estructura Notion-style: número grande, breakdown table, override panel.

```jsx
<section>
  <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">DETALLE</h3>
  {!cell ? (
    <EmptyState
      icon={MousePointer2}
      title="Selecciona una categoría"
      description="Elige una sigla de la lista para ver el conteo, ajustar manualmente y abrir los archivos."
    />
  ) : (
    <div className="rounded-xl bg-po-panel border border-po-border p-5">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="font-mono text-sm text-po-text">{cell.sigla}</span>
        <span className="text-po-text-muted">·</span>
        <span className="text-sm text-po-text">{SIGLA_LABELS[cell.sigla]}</span>
      </div>

      <p className="text-5xl font-semibold tabular-nums mt-4">{effectiveCount(cell).toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos</p>

      <div className="flex gap-2 mt-3">
        {isCompilationSuspect && <Badge variant="state-suspect" icon={FileStack}>Compilación</Badge>}
        <Badge variant={confidenceVariant(cell)}>{CONFIDENCE_LABEL[cell.confidence]}</Badge>
        {hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
      </div>

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Conteo automático</h4>
      <table className="w-full text-sm">
        <tbody>
          <tr><td className="text-po-text-muted py-1">Por nombre de archivo</td><td className="text-right font-mono tabular-nums">{cell.filename_count ?? "—"}</td></tr>
          <tr><td className="text-po-text-muted py-1">Por OCR</td><td className="text-right font-mono tabular-nums">{cell.ocr_count ?? "—"}</td></tr>
          <tr>
            <td className="text-po-text-muted py-1">Método</td>
            <td className="text-right text-sm">
              <Tooltip content={`Token interno: ${cell.method}`}>
                <span>{METHOD_LABEL[cell.method] ?? cell.method}</span>
              </Tooltip>
            </td>
          </tr>
        </tbody>
      </table>

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual</h4>
      <OverridePanel hospital={hospital} sigla={cell.sigla} cell={cell} />
    </div>
  )}
</section>
```

`METHOD_LABEL` constant:

```js
export const METHOD_LABEL = {
  filename_glob: "Nombre",
  header_detect: "Encabezados OCR",
  corner_count: "Recuadro de página",
  page_count_pure: "Conteo de páginas",
  manual: "Manual",
};

export const CONFIDENCE_LABEL = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
  manual: "Manual",
};
```

### 5.7 Files section

```jsx
<section>
  <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">ARCHIVOS</h3>
  {!cell ? (
    <EmptyState icon={MousePointer2} title="Selecciona una categoría" description="..." />
  ) : files === null ? (
    <div className="space-y-2"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
  ) : files.length === 0 ? (
    <EmptyState icon={FileX} title="Sin archivos" description="Esta categoría no tiene archivos PDF en este mes." />
  ) : (
    <div className="rounded-xl bg-po-panel border border-po-border">
      <div className="p-2 border-b border-po-border">
        <input
          placeholder="Buscar archivo…"
          className="w-full bg-transparent text-sm placeholder-po-text-subtle focus:outline-none px-2 py-1"
        />
      </div>
      <ul className="max-h-[60vh] overflow-y-auto">
        {filtered.map((f, i) => (
          <li key={f.name}>
            <button onClick={() => openLightbox(hospital, cell.sigla, i)}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-po-panel-hover text-left">
              <FileText size={14} className="text-po-text-muted shrink-0" />
              <span className="font-mono text-xs truncate flex-1">{f.name}</span>
              <span className="text-xs tabular-nums text-po-text-muted">{f.page_count}pp</span>
              {f.suspect && (
                <Tooltip content="Probable compilación">
                  <span><FileStack size={14} className="text-po-suspect" /></span>
                </Tooltip>
              )}
            </button>
          </li>
        ))}
      </ul>
      <div className="px-3 py-2 text-xs text-po-text-muted border-t border-po-border">
        {filtered.length} de {files.length}
      </div>
    </div>
  )}
</section>
```

### 5.8 `OverridePanel.jsx`

```jsx
function OverridePanel({ hospital, sigla, cell }) {
  const [value, setValue] = useState(cell.user_override ?? "");
  const [note, setNote] = useState(cell.override_note ?? "");
  const [saveStatus, setSaveStatus] = useState("idle");

  const save = useDebouncedCallback(async (v, n) => {
    setSaveStatus("saving");
    try {
      await store.saveOverride(sessionId, hospital, sigla, v === "" ? null : parseInt(v), n || null);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch {
      setSaveStatus("error");
    }
  }, 400);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <input
          type="number"
          value={value}
          onChange={e => { setValue(e.target.value); save(e.target.value, note); }}
          placeholder={String(cell.ocr_count ?? cell.filename_count ?? 0)}
          className="w-24 bg-po-bg border border-po-border rounded px-2 py-1.5 text-sm tabular-nums focus:border-po-accent outline-none"
        />
        <SaveIndicator status={saveStatus} />
      </div>
      <textarea
        value={note}
        onChange={e => { setNote(e.target.value); save(value, e.target.value); }}
        placeholder="Nota (opcional)"
        rows={3}
        className="w-full bg-po-bg border border-po-border rounded px-2 py-1.5 text-sm placeholder-po-text-subtle focus:border-po-accent outline-none resize-none"
      />
    </div>
  );
}
```

**Comportamiento:** debounce 400ms en cualquier change → save → SaveIndicator transiciona idle → saving → saved (2s) → idle. Error queda visible.

### 5.9 `PDFLightbox.jsx` (wrap con Radix Dialog)

```jsx
import * as Dialog from "@radix-ui/react-dialog";

function PDFLightbox() {
  const { lightbox, closeLightbox, ... } = useSessionStore();
  return (
    <Dialog.Root open={!!lightbox} onOpenChange={(o) => !o && closeLightbox()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/70" />
        <Dialog.Content className="fixed inset-4 bg-po-bg border border-po-border rounded-xl shadow-2xl flex flex-col">
          <header className="px-5 py-3 border-b border-po-border flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-mono text-po-text-muted">{hospital}</span>
                <span className="text-po-text-muted">·</span>
                <span className="font-mono text-po-text">{sigla}</span>
                <span className="text-po-text-muted">·</span>
                <span className="text-po-text">{SIGLA_LABELS[sigla]}</span>
              </div>
              <div className="font-mono text-xs text-po-text-muted truncate mt-0.5">{filename}</div>
            </div>
            <Dialog.Close className="text-po-text-muted hover:text-po-text">
              <X size={18} />
            </Dialog.Close>
          </header>
          <div className="flex-1 flex min-h-0">
            <div className="flex-1 bg-black">
              <iframe src={pdfUrl} className="w-full h-full border-0" title={filename} />
            </div>
            <aside className="w-80 border-l border-po-border p-4 overflow-y-auto">
              {/* Same DetalleSection minus the header/sigla — reuses MethodBreakdown + OverridePanel */}
              <CountSummary cell={cell} />
              <OverridePanel hospital={hospital} sigla={sigla} cell={cell} />
            </aside>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

Radix Dialog provee: focus trap, `Escape` close, portal management, body scroll lock, ARIA. El hand-rolled actual no tiene focus trap — esta mejora viene gratis con la lib.

### 5.10 `ScanControls.jsx`

Dos botones, copy pluralizado:

```jsx
<div className="flex gap-2">
  <Button
    disabled={selectedSiglas.length === 0}
    onClick={() => store.scanOcr(sessionId, selectedSiglas.map(s => [hospital, s]))}
    icon={Scan}
  >
    {selectedSiglas.length === 0
      ? "Selecciona categorías para OCR"
      : selectedSiglas.length === 1
        ? "Escanear 1 categoría"
        : `Escanear ${selectedSiglas.length} categorías`}
  </Button>
  {/* "OCR suspects de HPV" button MOVED to CategoryGroup header (§5.5) — remove from here */}
</div>
```

### 5.11 `ScanProgress.jsx`

Mantiene posición fixed-bottom y comportamiento de auto-dismiss. Cambios:

```jsx
<div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-po-panel border border-po-border rounded-xl shadow-2xl p-4 min-w-[400px]">
  <div className="flex items-center gap-3 mb-2">
    {progress.terminal === "complete" ? <CheckCircle2 size={16} className="text-po-success" />
     : progress.terminal === "cancelled" ? <X size={16} className="text-po-error" />
     : <Loader2 size={16} className="animate-spin text-po-scanning" />}
    <span className="text-sm font-medium">
      {progress.terminal === "complete" ? "Completado"
       : progress.terminal === "cancelled" ? "Cancelado"
       : "Escaneando…"}
    </span>
    <Badge variant="neutral" className="ml-auto"><span className="tabular-nums">{progress.done}/{progress.total}</span></Badge>
    {progress.etaMs && !progress.terminal && (
      <span className="text-xs text-po-text-muted">~{Math.round(progress.etaMs/1000)}s</span>
    )}
    {!progress.terminal && (
      <button onClick={cancel} className="text-xs text-po-error border border-po-error px-2 py-1 rounded hover:bg-po-error-bg">
        Cancelar
      </button>
    )}
  </div>
  <div className="h-1.5 bg-po-border rounded-full overflow-hidden">
    <div className="h-full bg-po-accent transition-all" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
  </div>
</div>
```

## 6. Interaction patterns

### 6.1 Inline-edit en count cells (Retool pattern)

- Click en number → input replaces it, value pre-selected
- Enter → commit (calls `store.saveOverride` con value como user_override)
- Escape → cancel, revert visual
- Blur → cancel (no commit) — Daniel debe hacer Enter explícito para guardar
- Mientras pending del WS round-trip, un dot pulsante violeta indica "edited, saving"

### 6.2 SaveIndicator timing

- `idle` → no render
- `saving` → loader spin + "Guardando…"
- `saved` → check + "Guardado" → 2s timer → idle
- `error` → alert + "No se pudo guardar" (no auto-dismiss; permanece hasta próximo intento)

### 6.3 Toasts (via sonner)

- Excel generation success → `toast.success("Excel guardado en {path}")` con `<FileSpreadsheet />` icon
- Excel generation error → `toast.error("No se pudo generar el Excel: {msg}")`
- OCR batch error (todos los workers fallaron) → `toast.error("OCR falló para {n} celdas")`
- Override save error → in-line SaveIndicator (NO toast — feedback local al campo)

### 6.4 Tooltips con jargon explanation

- Hover sigla en CategoryRow → tooltip con `SIGLA_LABELS[sigla]`
- Hover badge "Compilación" → tooltip `Probable compilación (PDF con >5× páginas esperadas)`
- Hover "Método: Nombre" → tooltip con token interno `Token interno: filename_glob`
- Hover dot de confidence en HospitalCard ribbon → tooltip con sigla + valor

### 6.5 Grouping (CategoryRow)

- Particionar por `cell.flags.includes("compilation_suspect")` al renderear HospitalDetail
- Cada grupo es collapsible, default open
- "Compilaciones" group header tiene action button `Escanear todas` (se passa la lista de compilación como cells)
- Si no hay compilaciones, no renderear la sección "Compilaciones"

### 6.6 Coordinación InlineEditCount ↔ OverridePanel (sin race conditions)

Ambos componentes escriben en el mismo campo: `cell.user_override`. La coordinación es **a través del store**, no entre componentes. Reglas:

1. **Único path de escritura**: `store.saveOverride(sessionId, hospital, sigla, value, note)`. Cualquier write desde cualquier componente pasa por aquí.

2. **Single pending-save por cell**: el store mantiene `_pendingSave: Map<string, AbortController>` keyed por `${hospital}|${sigla}`. Cualquier nueva llamada a `saveOverride` para esa key:
   - Aborta el debounce/in-flight previo
   - Cancela el `AbortController` previo (si el HTTP request ya estaba en flight, queda discardado al volver)
   - Instala el nuevo

3. **State source de OverridePanel**: el `value` y `note` del componente son **derived from `cell`** (`useEffect` que resincroniza cuando `cell.user_override` cambia, salvo si el usuario está activamente editando — detectado con un `isFocused` flag). Esto significa que un commit desde InlineEditCount actualiza `cell.user_override` vía store, el componente OverridePanel ve el cambio y resyncrioniza su input — no hay valor stale.

4. **Cancel de debounce en commit explícito**: cuando InlineEditCount llama a `onCommit` (Enter), llama directamente a `store.saveOverride` sin debounce y este cancela cualquier debounce pendiente de OverridePanel para esa key.

5. **Visual pending indicator**: el "estoy guardando" lo dibuja `SaveIndicator` en OverridePanel (Y el dot violeta pulsante en CategoryRow si el cell está mid-save). Ambos leen del mismo store flag `state.pendingSaves[key]: 'saving' | 'saved' | 'error' | undefined`.

6. **OverridePanel onBlur ≠ commit**: tipo en el input → debounce 400ms → save. Blur SOLO previene que el `isFocused` flag mantenga el valor stale; NO dispara un save adicional.

7. **InlineEditCount onBlur ≠ commit**: blur descarta el draft, NO guarda. El usuario tiene que apretar Enter explícitamente. Esto es consistente con el patrón Retool (Enter = commit, Esc/blur = cancel).

Resultado: si Daniel está editando en OverridePanel y simultáneamente alguien (o un retry de scan) cambia `cell.user_override`, su input local NO se sobrescribe mientras el campo tenga focus. Cuando hace blur, el componente resyncroniza con el último valor del store (su edición se pierde si no hizo blur con un debounce-flush — pero el debounce de 400ms suele ser suficiente, y el caso de race con write externo es marginal).

## 7. Acceptance criteria

Una sesión manual del implementer al final del plan debe verificar:

1. Abrir ABRIL → MonthOverview muestra 4 cards. HPV/HRB/HLU presentes con conteos + ribbon de 18 dots. HLL en empty state con botón "Ingresar conteos".
2. Click HPV → HospitalDetail con 2 secciones colapsables. Compilaciones tiene "Escanear todas" en su header.
3. Click en cualquier sigla → Detail panel a la derecha muestra: sigla + descripción + número grande tabular-nums + pills de estado + tabla de breakdown + override panel.
4. Click en el number de una celda en CategoryRow → input inline aparece, valor preseleccionado. Type new value, Enter → commit; el dot violeta de override aparece. Escape → cancela.
5. Type en `OverridePanel` → SaveIndicator transiciona saving → saved → idle.
6. Click en un PDF en FileList → Radix Dialog abre, focus trap funciona (Tab dentro del modal). Escape cierra. Click overlay cierra.
7. "Generar Excel del mes" → toast bottom-right "Excel guardado en {path}".
8. Trigger un OCR fallido (folder no exists) → toast error.
9. Grep audit final sobre **todo `frontend/src/**/*.jsx`** retorna **0 matches** para los patrones: `bg-slate-`, `bg-indigo-`, `bg-emerald-`, `bg-rose-`, `bg-amber-`, `border-slate-`, `border-indigo-`, `border-emerald-`, `text-slate-`, `text-indigo-`, `text-emerald-`. Es decir: cero clases de paleta cruda en TODO el frontend (no sólo componentes nuevos). Excepciones explícitas: `index.css` puede usar nombres Radix `var(--slate-*)` directamente porque ahí están definidas las variables, no son clases Tailwind. Si una clase legacy queda en un componente NO tocado por FASE 3, el implementer debe migrarla aunque sea un componente de borde — no hay Frankenstein theme. (Verificación al final del Chunk 4 como gating task.)
10. Verificar bundle size con `npm run build`: total gzipped del bundle main ≤ **baseline + 25 KB**. El baseline se mide en Chunk 1 task 0 antes de instalar deps nuevas y se commitea al spec en una nota al final de §10.
11. Sin errores en consola del browser durante el flow completo.
12. Inspección visual: ninguna emoji o glyph unicode visible (`⚠ ⟳ ✕ ✓ ○ ●` etc.); todos reemplazados por lucide icons.
13. Tooltips funcionan con delay 300ms.
14. CategoryRow row height ≤ 32px en compact mode.
15. Numerales en tabular-nums alineados verticalmente en la columna count.

## 8. Testing strategy

- **No nuevos tests automatizados de UI.** El stack actual no tiene RTL/Playwright wired; agregarlo es out-of-scope.
- **Manual smoke test** al final de cada chunk (per plan).
- **Visual regression manual** comparando antes/después de cada componente vía screenshots.
- **Accessibility quick-check**: navegación con Tab dentro del PDFLightbox debe quedar trapped; Escape cierra; focus retorna al trigger original (Radix Dialog garantiza esto).
- **Build sanity**: `npm run build` debe compilar sin warnings nuevos.
- **No regression backend**: `pytest` sigue verde (no cambios en `api/` o `core/` esperados — pero implementer corre suite al final).

## 9. Migration & rollout

- Branch `po_overhaul` continúa. No tag intermedio entre `fase-2-mvp` y `fase-3-polish` (la transición es continua).
- Tag final `fase-3-polish` al cierre del plan.
- No migración de datos (cell state schema no cambia).
- No migración de sessions persistidas (sigue funcionando con sessions creadas en FASE 2).

## 10. Risks

- **Bundle bloat**: Radix + sonner + lucide ~23 KB gzipped. Mitigación: tree-shake imports, `lucide-react` per-icon imports, no importar `@radix-ui/themes` (solo primitives).
- **Inline-edit UX confusion**: si Daniel está acostumbrado a abrir lightbox para corregir, inline-edit puede tomar tiempo aprender. Mitigación: el override panel sigue ahí para casos donde quiera ver el PDF antes de editar.
- **Microcopy gaps**: si una sigla no tiene label en `SIGLA_LABELS`, queda vacío. Mitigación: ground-truth desde `core/domain.py:CATEGORY_FOLDERS`; implementer verifica con Daniel cualquier label que rinda raro.
- **Radix bundle imports**: importar `@radix-ui/react-dialog` por sí solo (NO el paquete `@radix-ui/themes`) para mantener bundle chico.
- **Token rename ripple**: cada componente existente (no sólo los redesignados) usa clases Tailwind crudas de paleta (`bg-slate-800`, `bg-indigo-600`, etc.). Si la migración a `po-*` queda a medias y conviven clases crudas con tokens, la app se ve Frankenstein. Mitigación: AC9 endurecida (§7) hace un grep audit final sobre todo `frontend/src/**/*.jsx` que falla si queda CUALQUIER clase cruda. Chunk 4 incluye una task gating de "grep audit zero raw palette classes".
- **Layering: Dialog / Toaster / ScanProgress z-index**: 3 surfaces flotantes coexisten. Orden explícito requerido en `index.css` o como prop. Ladder: `z-40` ScanProgress (fixed-bottom), `z-50` Dialog Overlay, `z-51` Dialog Content, `z-60` Toaster (debe estar sobre el Dialog para mostrar errores aún en flow con modal abierto). Implementer wire este ladder en Chunk 1 task 4 cuando setea Toaster.
- **Bundle baseline**: AC10 referencia "baseline + 25 KB" pero el baseline necesita medirse. Chunk 1 task 0: `cd frontend && npm run build` antes de instalar deps; copiar `dist/assets/index-*.js` gzip size a un block "Bundle baseline: NN KB" al final de §10 mediante commit. Plan implementer reemplaza el placeholder.

**Bundle baseline (medido en Chunk 1):** _<placeholder — implementer measures and commits actual gzipped size of `frontend/dist/assets/index-*.js` on tip-of-`po_overhaul` before Chunk 1 installs>_

## 11. Dependencies (new)

A agregar a `frontend/package.json`:

```json
{
  "@fontsource/inter": "^5.0.0",
  "@fontsource/jetbrains-mono": "^5.0.0",
  "@radix-ui/colors": "^3.0.0",
  "@radix-ui/react-dialog": "^1.0.0",
  "@radix-ui/react-tooltip": "^1.0.0",
  "lucide-react": "^0.400.0",
  "sonner": "^1.0.0"
}
```

No agregar `windy-radix-palette` (ver §4.1 — usamos CSS variables directas). No agregar `use-debounce` — hand-rollear un `useDebouncedCallback` hook de ~10 líneas en `lib/hooks/useDebouncedCallback.js` para evitar la dep.

## 12. Implementation chunks

**Chunk 1 — Cleanup + foundation (~6 tasks)**
0. **Measure bundle baseline**: `cd frontend && npm run build`, anotar gzipped size de `dist/assets/index-*.js` y commitear ese número reemplazando el placeholder en §10. Esto es task 0 — antes de instalar nada.
1. Delete dead components: `HeaderBar.jsx`, `Sidebar.jsx`, `ProgressBar.jsx`, `ScanIndicator.jsx`, `components/README.md`
2. Delete dead exports en `lib/constants.js` (SPINNER, IMPACT_LABELS, formatTime)
3. Install new deps via `npm install` (sin `windy-radix-palette` ni `use-debounce`)
4. Wire fonts via `@fontsource/inter` + `@fontsource/jetbrains-mono` in `main.jsx`
5. Wire `frontend/src/index.css` con `@import "@radix-ui/colors/<name>-dark.css"` (6 paletas) + `tailwind.config.js` con tokens semánticos `po-*` referenciando `var(--<scale>-N)`. Add `<Toaster position="bottom-right" theme="dark" />` en App.jsx con z-60. Define z-index ladder en CSS layer.

**Chunk 2 — UI primitives (~8 tasks, una por primitivo)**
6. `ui/Button.jsx` (primer primitivo — bloquea a varios otros)
7. `ui/Badge.jsx`
8. `ui/Dot.jsx`
9. `ui/SaveIndicator.jsx`
10. `ui/EmptyState.jsx` (depende de Button)
11. `ui/Skeleton.jsx`
12. `ui/Tooltip.jsx` (wraps Radix Tooltip)
13. `ui/Dialog.jsx` (wraps Radix Dialog)

**Chunk 3 — Constants + Components redesign (~11 tasks)**
14. `lib/sigla-labels.js` + `lib/method-labels.js` (con confidence labels)
15. `lib/hooks/useDebouncedCallback.js` (hand-rolled, ~10 líneas)
16. Store extension: `_pendingSave: Map` + `saveOverride` con AbortController (§6.6)
17. `MonthOverview.jsx` redesign (sin "FASE 2" subtitle, toast en lugar de alert, copy mejorado)
18. `HospitalCard.jsx` redesign (ribbon de dots + timestamp + Building2 icon)
19. `HospitalCard.jsx` empty state HLL (`<FolderX/>` + EmptyState + Button "Ingresar conteos" → comportamiento del CTA: por ahora abre un panel inline con 18 OverridePanels apilados; si excede polish scope, deferir explicitamente con un Button disabled + Tooltip "Disponible en FASE 4" y mover la feature al spec FASE 4 vía PR doc-update separado)
20. `HospitalDetail.jsx` header redesign (ArrowLeft icon, Total tabular-nums)
21. `CategoryGroup.jsx` (nuevo componente) + grouping logic por `compilation_suspect` flag en HospitalDetail
22. `CategoryRow.jsx` redesign (single-line, Dot + Badge + InlineEditCount con coordinación store)
23. Detail section reimplementación (Notion-style: número grande + breakdown table + pills + OverridePanel)
24. `FileList.jsx` redesign (Skeleton loaders, EmptyState, FileText icons, font-mono filenames con truncate)
25. `PDFLightbox.jsx` redesign (wraps Radix Dialog — focus trap + a11y; header 2-line; right panel mirrors Detail layout)

**Chunk 4 — Polish + audit + smoke (~5 tasks)**
26. `OverridePanel.jsx` redesign con SaveIndicator integrado + debounce + store coordination
27. `ScanControls.jsx` redesign (copy pluralizado; mover "OCR suspects" → header de CategoryGroup "Compilaciones")
28. `ScanProgress.jsx` redesign (icons, Badge, ETA, destructive Cancel button, z-40)
29. **Grep audit gating**: `cd frontend && grep -rE "bg-slate-|bg-indigo-|bg-emerald-|bg-rose-|bg-amber-|border-slate-|border-indigo-|border-emerald-|text-slate-|text-indigo-|text-emerald-" src/**/*.jsx` debe retornar EMPTY. Si encuentra hits, migrar antes de seguir. NO mergeable hasta cero.
30. Manual smoke test end-to-end (los 15 acceptance criteria de §7), update CLAUDE.md con nueva paleta + nuevas deps, tag `fase-3-polish`.

**Estimado total:** ~30 tareas. SDD con haiku implementers debería tardar 5-7 horas (incluyendo review loops). Chunk 3 task 19 tiene un fork de decisión (HLL CTA — implementar vs deferir) que el plan debe pre-resolver consultando con Daniel.

---

**Spec status:** Pendiente review por subagent + Daniel.
