# `tests/fixtures/scanners/` — OCR scanner fixtures

Snapshot PDFs + ground truth for the per-sigla OCR scanner smoke tests
(`tests/unit/scanners/test_pattern_*.py`).

## Why the PDFs are not in git

The repository `.gitignore` excludes `*.pdf`. **Only the `ground_truth.json`
files are committed**; the fixture PDFs are local-only snapshots extracted
from the read-only corpus at `A:\informe mensual\ABRIL\`. Each smoke test is
guarded with `pytest.skip(...)` when its fixture PDF is absent, so a fresh
clone (or CI without the corpus) stays green.

To recreate the fixtures on a new machine, re-extract the page(s) named in
each `ground_truth.json` from the corresponding `A:\informe mensual\<MES>\`
PDF with PyMuPDF. When working in a git worktree, copy the gitignored
fixtures over from the main worktree.

## Layout

```
tests/fixtures/scanners/<sigla>/
    <fixture>.pdf            # local-only snapshot
    ground_truth.json        # committed
```

Multi-flavor siglas (e.g. `chintegral`, `dif_pts`) may instead use one
sub-directory per flavor, each with its own fixture + `ground_truth.json`:

```
tests/fixtures/scanners/<sigla>/<flavor>/
    <fixture>.pdf
    ground_truth.json
```

**Fixture naming (decision A9 / A15):** `f_<código>_p<pages>_<descripción>.pdf`
— e.g. `f_lch_05_p2p5_chequeo_hrb.pdf`, `f_ch_crs_01_2p_cover_shadow.pdf`.
Anti-anchor "shadow" fixtures (a page that must NOT count) are named
`*_shadow_<reason>.pdf`.

## `ground_truth.json`

Two shapes are in use:

Single fixture:

```json
{
  "fixture": "f_art_01_p1_crs_andamios.pdf",
  "pages": 2,
  "covers_expected": 1,
  "notes": "What the PDF is and why covers_expected is what it is."
}
```

Multiple fixtures (one entry per flavor / shadow):

```json
{
  "fixtures": [
    {"file": "f_rch_p1_x.pdf", "pages": 1, "covers_expected": 1, "notes": "..."},
    {"file": "f_..._shadow_x.pdf", "pages": 2, "covers_expected": 0,
     "notes": "shadow page — anti-anchors must reject it"}
  ],
  "notes": "Optional sigla-level notes."
}
```

`covers_expected` is the number of **document covers** the scanner must
count in that PDF — established by visually inspecting every page, never
assumed. It must be honest: a 2-cover compilation has `covers_expected: 2`.

## Running the smoke tests

```bash
pytest tests/unit/scanners/test_pattern_<sigla>.py -v   # one sigla
pytest tests/unit/scanners/ -q                          # all scanner tests
```

The anchor smokes run real Tesseract OCR; the `insgral` / `altura` smokes
run the full V4 pipeline. Expect tens of seconds per multi-page fixture.

## A13 — adding a new flavor when an unexpected PDF appears

When the corpus surfaces a template that no flavor matches (the scanner
reports it via near-match telemetry — A14), follow the A13 maintenance
protocol:

1. **Ver portada** — open the PDF's first page in the viewer.
2. **Classify** — is it a real variant of an existing sigla, or out of scope?
3. **Extend or create** — widen an existing flavor's anchors, or add a new
   flavor to that sigla's entry in `core/scanners/patterns.py`. Anchors must
   be structural text (titles, field labels, pagination) — never raw form
   codes (decision A12; a form-code family prefix is the most allowed).
4. **Snapshot** — extract a fixture PDF here under the sigla, named per A9.
5. **Ground truth** — add/update `ground_truth.json` with the honest count.
6. **Smoke** — add a smoke assertion and confirm it passes.
7. Bump `SCANNER_PATTERNS_VERSION` in `core/utils.py`.
