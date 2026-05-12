# Scanners OCR fixtures

Real PDFs extracted from `A:\informe mensual\ABRIL\` via
`tools/extract_fase2_fixtures.py`. Each fixture lives in a sub-folder
containing exactly one PDF — scanners use `folder.glob("*.pdf")`, so
they need a folder shape, not a flat file.

| Folder | PDF | Source | Min pages (compilation threshold) | Used by |
|---|---|---|---|---|
| art_multidoc/ | art_multidoc.pdf | HLU/7.-ART | 50 | corner_count, art_scanner tests |
| odi_compilation/ | HRB_odi_compilation.pdf | HRB/3.-ODI Visitas | 10 | header_detect, odi_scanner tests |
| irl_compilation/ | HRB_irl_compilation.pdf | HRB/2.-Induccion IRL | 10 | header_detect, irl_scanner tests |
| charla_compilation/ | HRB_charla_compilation.pdf | HRB/4.-Charlas | 10 | page_count_pure, charla_scanner tests |
| corrupted/ | corrupted.pdf | synthetic (0-byte) | — | error handling tests only |

Per memory `feedback_art670_fixture_disaster`: real fixtures only.
`corrupted.pdf` is allowed because it's a degenerate-input fixture for
error tests, not data substitution.

**Refreshing.** Re-run `python tools/extract_fase2_fixtures.py` after
the source corpus changes. The script asserts the page-count threshold
per sigla and exits non-zero if any picked PDF is below the
compilation_suspect cutoff — fix that before committing the refreshed
fixtures.
