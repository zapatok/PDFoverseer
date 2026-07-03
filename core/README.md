# PDFoverseer Core

Motor de conteo: glob de nombre/token (pase 1) + escáneres OCR (pase 2), resolución
de conteo por celda, la capa SQLite, y el escritor de Excel. También retiene el
pipeline OCR+inferencia V4 original como *fallback* diferido, en cuarentena
(no conectado a nada).

## Archivos

- `domain.py` — hospitales, siglas, constantes de carpetas de categoría (fuente única)
- `cell_count.py` — `compute_cell_count`/`compute_worker_count`, el único lugar donde convergen UI/Excel/historial
- `utils.py` — constantes del pipeline/inferencia, dataclasses compartidas, regex
- `image.py` / `ocr.py` / `pipeline.py` / `inference.py` — el motor V4 diferido
- `scanners/` — la tríada de escáneres de pase 2 (`SimpleFilenameScanner`/`AnchorsScanner`/`PaginationScanner`) + el registro `patterns.py`
- `orchestrator/` — enumeración de meses, despacho de pase 1/pase 2
- `excel/` — plantilla RESUMEN + escritor
- `db/` — conexión SQLite, migraciones, repos de sesión + histórico
- `state/` — migraciones del esquema de estado de sesión

**La arquitectura y convenciones viven en `core/CLAUDE.md`** — este archivo
intencionalmente delega a ese documento.
