# docs/archive/

Historical design/research docs for **abandoned or unmerged** experiments, moved here
during the 2026-06-21 pre-master audit to declutter the active `docs/` tree. They are kept
(not deleted) as a record; nothing in the codebase or active docs references them.

| Doc | What it was | Why archived |
|-----|-------------|--------------|
| `2026-03-15-crop-selector-design.md` / `2026-03-15-crop-selector.md` | UI crop-region selector | Unmerged feature (`feature/crop-selector` branch) |
| `2026-03-15-ocr-matcher.md` | Fuzzy OCR pattern generator | Unmerged feature (`feature/ocr-matcher` branch) |
| `2026-04-11-dit-classifier-lofo.md` | DiT classifier LOFO eval | DiT cover-classifier research (not adopted) |
| `2026-04-11-dit-cosine-canonical-fixtures.md` | DiT cosine vs canonical fixtures | DiT research (not adopted) |
| `2026-04-11-dit-cosine-rio-bueno-benchmark.md` | DiT cosine rio-bueno benchmark | DiT research (not adopted) |
| `2026-04-01-pd-v3-error-analysis.md` | Pixel-density v3 error analysis | pixel-density research (lives on `research/pixel-density`) |
| `2026-04-01-pixel-density-advanced-sweep-results.md` | Pixel-density advanced sweep | pixel-density research |
| `2026-04-06-scorer-forms-results.md` | Form-scorer experiment results | pixel-density/scorer research (not adopted) |

The pixel-density / DiT eval code these document was deleted from `po_overhaul` in the same
audit (recoverable from git history; pixel-density also lives on the `research/pixel-density`
branch). The active record of *shipped* work stays under `docs/superpowers/{specs,plans}/`.
