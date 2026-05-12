# Archivos con naming irregular — ABRIL 2026

Generado por `tools/audit_filename_glob.py` el 2026-05-12.

El scanner `core.scanners.utils.filename_glob.extract_sigla` exige el patrón estricto
`YYYY-MM-DD_sigla[_<extra>]*.pdf` (definido aguas arriba en el proyecto
`A:\informe mensual\`). Los archivos abajo violan el patrón y no se cuentan en
el scan automático.

## HPV — 10 archivos con fecha abreviada (`YYYY-MM_…`, sin día)

Estos sí afectan el Excel — son 10 PDFs que actualmente no se cuentan.

| Carpeta | Archivo |
|---|---|
| `6.-Difusion PTS` | `2026-04_dif_pts_o2.pdf` |
| `8.-Inspecciones Generales/STI` | `2026-04_insgral_chequeo_comedores_vestidores_y_duchas_sti.pdf` |
| `8.-Inspecciones Generales/STI` | `2026-04_insgral_chequeo_de_epp_sti.pdf` |
| `8.-Inspecciones Generales/STI` | `2026-04_insgral_chequeo_de_orden_y_aseo_sti.pdf` |
| `10.-Inspeccion de Maquinaria/KOHLER` | `2026-04_maquinaria_chequeo_plataformas_elevadoras_kohler.pdf` |
| `10.-Inspeccion de Maquinaria/KOHLER` | `2026-04_maquinaria_chequeo_semanal_de_roscadora_kohler.pdf` |
| `11.-Extintores/STI` | `2026-04_ext_chequeo_sti.pdf` |
| `15.-Inspeccion Trabajos en Caliente/STI` | `2026-04_caliente_chequeo_sti.pdf` |
| `16.-Inspeccion Herramientas Electricas/KOHLER` | `2026-04_herramientas_elec_chequeo_esmeril_angular_kholer_kohler.pdf` |
| `16.-Inspeccion Herramientas Electricas/KOHLER` | `2026-04_herramientas_elec_chequeo_extenciones_kholer_kohler.pdf` |

**Acción:** renombrar agregando un día (puede ser `01` para chequeos mensuales agregados, o el día real del documento). Ejemplo:
`2026-04_ext_chequeo_sti.pdf` → `2026-04-01_ext_chequeo_sti.pdf`

Tras el renombrado, la auditoría debería reportar 0/54 discrepancias.

## HLL — 100 archivos en `28. Abril 2026/Resumen Ejecutivo_HLL_Abril 2026/…`

Estos NO afectan el Excel actual: HLL completo está marcado `hospitals_missing` por el
orchestrator porque no tiene las 18 carpetas canónicas (`1.-Reunion Prevencion`, etc).
Es la prueba documental de "HLL no normalizado todavía" — la normalización aguas arriba
de este hospital es un trabajo aparte.

Lista corta de los 100 archivos: ver salida completa de
`python tools/audit_filename_glob.py`.

## Cómo regenerar este reporte

```bash
python tools/audit_filename_glob.py
```

Lista todos los `(hospital, sigla)` con `SCAN`, `RAW`, `NONE` (filenames no reconocidos
por el regex), y marca `DISCREPANCY` cuando `SCAN != RAW`.
