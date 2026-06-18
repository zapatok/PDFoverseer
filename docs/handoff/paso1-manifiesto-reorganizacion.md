# Contrato del manifiesto de reorganización — Paso 1

**Versión de manifiesto:** 1
**Emitido por:** PDFoverseer (rama `po_overhaul`)
**Fecha del documento:** 2026-06-17

---

## 1. Qué es y por qué existe

PDFoverseer analiza los PDFs del mes, cuenta los documentos por celda
`(hospital, sigla)` y detecta documentos mal clasificados o colados: por
ejemplo, un ODI incluido dentro de `art_crs.pdf`, o un archivo que pertenece
a otra sigla.

El **manifiesto de reorganización** (`reorganizacion_<YYYY-MM>.json`) es el
documento declarativo que le dice al paso 1 cómo dejar el archivo físico
coherente con lo que los libros de PDFoverseer ya reflejan. PDFoverseer ya
ajustó los conteos del mes en el momento en que se marcaron las operaciones;
el manifiesto le indica al paso 1 cuáles movimientos, extracciones o
rotaciones ejecutar para que la carpeta del mes quede alineada con esos
conteos.

---

## 2. Dónde leerlo

```
<OVERSEER_OUTPUT_DIR>/reorganizacion_<YYYY-MM>.json
```

`OVERSEER_OUTPUT_DIR` es la carpeta de salidas de PDFoverseer (por defecto
`data/outputs` dentro del proyecto). El manifiesto **no** vive dentro de
`A:\informe mensual` — ese corpus es de solo lectura para PDFoverseer.

Ejemplo de ruta real:
```
A:\PROJECTS\PDFoverseer\data\outputs\reorganizacion_2026-06.json
```

---

## 3. Cuándo ejecutarlo

Ejecutar el manifiesto **entre el Step 3 y el Step 4** del workflow del paso 1:

- **Step 3 (contar):** el paso 1 contó los archivos de cada celda.
- **→ Aquí ejecutar el manifiesto** (mover, extraer, rotar).
- **Step 4 (totalizar a nombres de carpeta):** el paso 1 renombra y totaliza.

Si el manifiesto se ejecuta después del Step 4, los nombres canónicos ya
habrán sido asignados y el manifiesto apuntará a nombres que ya no existen.

---

## 4. Contrato campo por campo

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | `str` | `op_NNN` correlativo dentro de la sesión, estable. |
| `op_type` | `str` | uno de `move_file` / `extract_pages` / `split_in_place` / `rotate`. |
| `source` | `dict` | `{hospital, sigla, file, page_range?}`. `file` = nombre actual del PDF (cómo el paso 1 lo encuentra). `page_range` = `[inicio, fin]` (1-based, inclusivo) o ausente = archivo completo. |
| `dest` | `dict` | `{hospital, sigla}`. Cualquier celda. **Intención**, no filename. |
| `empresa` | `str \| null` | pista para el nombre canónico que arma el paso 1. Opcional. |
| `preserve_date` | `bool` | default `true`: conserva la fecha del documento original al renombrar. |
| `rotation_deg` | `int` | `0` / `90` / `180` / `270`. Default `0`. |
| `doc_count` | `int` | cuántos documentos viajan (ver tabla de conteo). |
| `worker_count` | `int` | cuántos trabajadores/chequeos viajan (0 si la celda no es de trabajadores). |
| `note` | `str \| null` | comentario libre del operador. |
| `status` | `str` | `pending` / `applied`. Informativo + lifecycle interno. Nace `pending`. |

### Tipos y su efecto en el conteo

| Tipo | Qué hace | `source.page_range` | Delta de conteo |
|------|----------|---------------------|-----------------|
| `move_file` | archivo completo F: `(hosp, sigla_orig)` → `(hosp, sigla_dst)`. **Reclasificar = mover a otra sigla.** | ausente | origen `−doc_count`, destino `+doc_count`. `doc_count` default = contribución actual de F a la celda (`per_file_overrides[F] \| per_file[F] \| 1`). |
| `extract_pages` | páginas X–Y de F → `(hosp, sigla_dst)` (el doc colado) | `[X, Y]` | origen `−doc_count`, destino `+doc_count`. `doc_count` default `1`, tope ≤ (Y−X+1). |
| `split_in_place` | partir F en N documentos dentro de la **misma** celda | opcional | sin cambio de conteo (`doc_count = 0`; informa al paso 1 que separe). |
| `rotate` | rotar F o páginas X–Y `rotation_deg°` | opcional | sin cambio de conteo (`doc_count = 0`). |

`worker_count` (celdas `documents_workers` / `checks`): para `move_file` = suma de `count` de las marcas del archivo F; para `extract_pages` = suma de las marcas en páginas X–Y; `0` en celdas `documents`.

---

## 5. Ejemplo de manifiesto

```json
{
  "manifest_version": 1,
  "generated_at": "2026-06-17T14:30:00",
  "source_project": "PDFoverseer",
  "month": "2026-06",
  "operations": [
    {
      "id": "op_001",
      "op_type": "extract_pages",
      "source": { "hospital": "HRB", "sigla": "art", "file": "art_crs.pdf", "page_range": [45, 47] },
      "dest":   { "hospital": "HRB", "sigla": "odi" },
      "empresa": null,
      "preserve_date": true,
      "rotation_deg": 0,
      "doc_count": 1,
      "worker_count": 0,
      "note": "ODI colado en el compilado de ART",
      "status": "pending"
    }
  ]
}
```

---

## 6. En qué fijarse al implementar la ejecución

### El destino es intención, no un nombre de archivo

`dest.hospital` y `dest.sigla` expresan **adónde debe ir el documento**; no
indican un nombre de archivo de destino. El paso 1 construye el nombre
canónico con su propia convención:

```
fecha_sigla_descriptor_empresa.pdf
```

usando `COMPANY_CORRECTIONS` y sus reglas habituales. No hay que inventar un
nombre literal a partir del manifiesto.

### `preserve_date`

Cuando `preserve_date: true` (valor por defecto), conservar la fecha del
documento original al renombrar. Si el archivo de origen tiene una fecha
en su nombre (`YYYY-MM-DD_...`), usarla como fecha del destino, en lugar de
la fecha actual.

### Orden de las extracciones del mismo archivo

Si hay múltiples operaciones `extract_pages` sobre el **mismo archivo fuente**,
sus rangos son siempre disjuntos por validación de PDFoverseer. Sin embargo,
al extraer contra el archivo original, los índices de página no corren.
Aplicar las extracciones en cualquiera de estas formas equivalentes:
- En **orden de página descendente** (de mayor a menor número de página), de
  modo que la extracción de páginas altas no afecte los índices de las bajas.
- O bien trabajar siempre contra una **copia intacta** del original, lo que
  hace que el orden sea irrelevante.

Ambos enfoques garantizan que `page_range: [45, 47]` se refiere siempre a las
páginas 45–47 del archivo original, independientemente de cuántas
extracciones anteriores se hayan realizado.

### Idempotencia

Antes de ejecutar cada operación, verificar si el destino ya contiene el
archivo esperado. Si ya está presente, registrar la operación como ya
aplicada y continuar sin duplicar. Esto permite re-correr el manifiesto sin
consecuencias si una ejecución anterior se interrumpió a mitad.

### Reportar remanentes

Después de ejecutar todas las operaciones, reportar los archivos que quedaron
sin procesarse (por ejemplo, el fragmento remanente de un `extract_pages` en el
archivo original). El paso 1 ya tiene una lógica de reportes de remanentes;
aplicar el mismo patrón.

### Patrón `--ejecutar` del paso 1

El manifiesto se procesa siguiendo el patrón `--ejecutar` del paso 1:
primero un **dry-run** (sin modificar nada) que muestra qué se haría, luego
la ejecución real solo si el dry-run no muestra errores. No saltarse el
dry-run aunque el manifiesto sea pequeño.

### El campo `status` es informativo

`status` comienza como `pending`. El paso 1 puede registrar `applied` en su
propio log cuando completa una operación. PDFoverseer **no** lee este campo de
vuelta para tomar decisiones de conteo — usa la evidencia del sistema de
archivos (presencia o ausencia del archivo fuente en su carpeta original).
Registrar el estado completado en el log del paso 1 es útil para auditoría,
pero no es obligatorio para que PDFoverseer funcione correctamente.

---

## 7. Referencia

- Spec de diseño: `docs/superpowers/specs/2026-06-17-incremento-J-reorganizacion-manifiesto-design.md` (§4, §7, §10)
- Versión del manifiesto: `1` (field `manifest_version` en el JSON)
- Generado por: `POST /api/sessions/{id}/reorg/export` → escribe en `OVERSEER_OUTPUT_DIR`
