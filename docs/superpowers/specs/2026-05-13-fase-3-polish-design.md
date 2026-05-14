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

Adoptar `@radix-ui/colors` para tener una escala de 12 pasos con propósito documentado por step. Mapear via `windy-radix-palette` Tailwind plugin para usarlos como clases (`bg-jadeDark-9` etc.). Sobre esa base, definir tokens **semánticos** en `tailwind.config.js`:

```js
// tailwind.config.js — theme.extend.colors
{
  'po-bg':              'var(--slateDark-1)',     // #111113
  'po-panel':           'var(--slateDark-2)',     // #18191b
  'po-panel-hover':     'var(--slateDark-3)',     // #1d1e1f
  'po-border':          'var(--slateDark-6)',     // #2a2b2e
  'po-border-strong':   'var(--slateDark-7)',     // #36373a
  'po-text':            'var(--slateDark-12)',    // #edeef0
  'po-text-muted':      'var(--slateDark-11)',    // #b0b4ba
  'po-text-subtle':     'var(--slateDark-10)',    // #7e8389

  'po-confidence-high': 'var(--jadeDark-11)',     // #3dd68c
  'po-confidence-low':  'var(--amberDark-11)',    // #f1a10d

  'po-suspect':         'var(--amberDark-9)',     // #ffb224
  'po-suspect-bg':      'var(--amberDark-3)',     // amberDark.3
  'po-error':           'var(--rubyDark-11)',     // #ff8b9c
  'po-error-bg':        'var(--rubyDark-3)',
  'po-scanning':        'var(--indigoDark-10)',   // pulsing
  'po-override':        'var(--irisDark-11)',     // #b1a9ff
  'po-override-bg':     'var(--irisDark-3)',
  'po-success':         'var(--jadeDark-11)',

  'po-accent':          'var(--indigoDark-9)',    // #3e63dd primary CTA
  'po-accent-hover':    'var(--indigoDark-10)',
}
```

**Regla:** ninguna clase Tailwind `bg-slate-*`, `bg-indigo-*`, `bg-emerald-*` etc. directa en JSX. Todo color pasa por un token `po-*`. Un linter check del implementer puede grep-buscar `bg-slate-` post-implementación para verificar.

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

1. **`Badge.jsx`** — `<Badge variant="confidence-high" icon={CheckCircle2}>Alta</Badge>`. Variants: `confidence-high`, `confidence-low`, `state-suspect`, `state-scanning`, `state-error`, `state-override`, `neutral`. Forma: `rounded-full px-2 py-0.5 text-[11px] font-medium inline-flex items-center gap-1 border`.

2. **`Dot.jsx`** — `<Dot variant="confidence-high" />`. 8×8 `rounded-full` solid color. Used in CategoryRow + HospitalCard ribbon.

3. **`SaveIndicator.jsx`** — controlled prop `status: 'idle' | 'saving' | 'saved' | 'error'`. Idle: nothing rendered. Saving: `<Loader2 size={12} className="animate-spin" /> Guardando…` en `text-po-text-muted`. Saved: `<CheckCircle2 size={12} className="text-po-success" /> Guardado` fades after 2s. Error: `<AlertCircle size={12} className="text-po-error" /> No se pudo guardar`.

4. **`EmptyState.jsx`** — `<EmptyState icon={FileX} title="..." description="..." action={<Button>...</Button>} />`. Geist recipe.

5. **`Skeleton.jsx`** — `<Skeleton className="h-4 w-12" />`. `bg-po-panel-hover animate-pulse rounded`.

**Radix-wrapped (a11y critical):**

6. **`Tooltip.jsx`** — wraps `@radix-ui/react-tooltip`. API: `<Tooltip content="...">{trigger}</Tooltip>`. Provider sits at App level with `delayDuration={300}`.

7. **`Dialog.jsx`** — wraps `@radix-ui/react-dialog`. API: `<Dialog open={...} onOpenChange={...}><Dialog.Header>...</Dialog.Header><Dialog.Body>...</Dialog.Body></Dialog>`. Used by PDFLightbox.

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

**Constante nueva:** `frontend/src/lib/sigla-labels.js`:

```js
export const SIGLA_LABELS = {
  reunion: "Acta de reunión",
  irl: "Inspección reglamentaria de luminarias",
  odi: "Observación de inspección",
  charla: "Charla de seguridad",
  chintegral: "Charla integral",
  dif_pts: "Difusión de puntos",
  art: "Análisis de riesgo de trabajo",
  insgral: "Inspección general",
  bodega: "Inspección de bodega",
  maquinaria: "Inspección de maquinaria",
  ext: "Inspección de extintores",
  senal: "Inspección de señalización",
  exc: "Excavación",
  altura: "Trabajo en altura",
  caliente: "Trabajo en caliente",
  herramientas_elec: "Herramientas eléctricas",
  andamios: "Andamios",
  chps: "Charla preventiva semanal",
};
```

(Implementer: si una etiqueta no es exacta, consultar con Daniel o dejar como placeholder con un TODO inline — pero NO inventar significados).

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
9. Verificar grep `bg-slate-` y `bg-indigo-` en JSX retorna **0 matches** en componentes nuevos.
10. Verificar bundle size con `npm run build`: total bundle gzipped ≤ current + 25 KB.
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
- **Microcopy gaps**: si una sigla no tiene label en `SIGLA_LABELS`, queda vacío. Mitigación: TODO inline en la constante; implementer verifica con Daniel siglas dudosas.
- **Radix bundle imports**: importar `@radix-ui/react-dialog` por sí solo (NO el paquete `@radix-ui/themes`) para mantener bundle chico.

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
  "sonner": "^1.0.0",
  "windy-radix-palette": "^2.0.0",
  "use-debounce": "^10.0.0"
}
```

(`use-debounce` para el debounce 400ms en OverridePanel autosave; alternativamente hand-roll un hook si Daniel prefiere zero-dep.)

## 12. Implementation chunks

**Chunk 1 — Cleanup + foundation (~4 tasks)**
1. Delete dead components: `HeaderBar.jsx`, `Sidebar.jsx`, `ProgressBar.jsx`, `ScanIndicator.jsx`, `components/README.md`
2. Delete dead exports en `lib/constants.js` (SPINNER, IMPACT_LABELS, formatTime)
3. Install new deps + wire fonts via `@fontsource/*` in `main.jsx`
4. Wire `tailwind.config.js` con Radix Colors via `windy-radix-palette` + tokens semánticos `po-*`. Add Toaster en App.jsx.

**Chunk 2 — UI primitives (~7 tasks, una por primitivo)**
5. `ui/Badge.jsx`
6. `ui/Dot.jsx`
7. `ui/SaveIndicator.jsx`
8. `ui/EmptyState.jsx`
9. `ui/Skeleton.jsx`
10. `ui/Tooltip.jsx` (wraps Radix)
11. `ui/Dialog.jsx` (wraps Radix)

**Chunk 3 — Components redesign (~10 tasks)**
12. `lib/sigla-labels.js` + `lib/method-labels.js`
13. `MonthOverview.jsx` redesign (sin FASE 2, toast en lugar de alert, copy mejorado)
14. `HospitalCard.jsx` redesign (ribbon de dots + timestamp)
15. `HospitalCard.jsx` empty state HLL
16. `HospitalDetail.jsx` header redesign
17. `CategoryGroup.jsx` (nuevo) + grouping logic en HospitalDetail
18. `CategoryRow.jsx` redesign (single-line, Dot + Badge + InlineEditCount)
19. Detail section (Notion-style con number + breakdown + OverridePanel)
20. `FileList.jsx` redesign
21. `PDFLightbox.jsx` redesign (Radix Dialog wrap)

**Chunk 4 — Polish + smoke (~3 tasks)**
22. `OverridePanel.jsx` con SaveIndicator + debounce
23. `ScanControls.jsx` + `ScanProgress.jsx` redesign
24. Manual smoke test end-to-end + actualizar CLAUDE.md con nueva paleta + tag `fase-3-polish`

**Estimado total:** ~24 tareas. SDD con haiku implementers debería tardar 4-6 horas.

---

**Spec status:** Pendiente review por subagent + Daniel.
