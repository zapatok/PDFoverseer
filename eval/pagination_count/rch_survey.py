"""Fase 0 — RCH corner survey (Track D / D2, spec §3).

Characterizes the RCH template's repeated-pagination bug BEFORE any de-dup
approach is designed (spec: "Ningún diseño se fija antes de esto"). For every
page of the charla samples under ``data/samples/`` this script OCRs three
candidate regions:

- ``current``       — the production pagination corner, ``_CORNER_PORTRAIT``
                       from ``core/scanners/utils/pagination_count.py``
                       (``(0.50, 0.0, 1.0, 0.15)``).
- ``amplified``      — a wider corner candidate (``(0.35, 0.0, 1.0, 0.20)``).
- ``top_left_half``  — the opposite side of the page (``(0.0, 0.0, 0.5,
                       0.20)``) — does NOT contain the pagination corner at
                       all; tests whether cover-only fields also live there.

and records, per (page, region): the raw OCR text, ``parse_pagination``,
``extract_code``, and which ``CRS_RCH_ANCHORS`` (the proven cover-only
discriminator the anchors engine already uses) match.

For samples whose page count is an exact multiple of the GT document count
(homogeneous N-page-per-doc compilations — no page-level cover/continuation
labels exist otherwise), page parity gives a reliable expected role (page
``i`` is a cover iff ``i % N == 0``), which lets this script measure a real
hit-rate/false-positive-rate per region instead of only descriptive stats.

Usage (from project root, with venv active)::

    python eval/pagination_count/rch_survey.py

Writes the raw per-page dump to
``eval/pagination_count/results/rch_survey.json`` (gitignored) and prints the
summary tables consumed by ``docs/research/2026-07-12-rch-corner-survey.md``.

DATA-SAFETY: reads only ``data/samples/*.pdf`` (committed, read-only sample
corpus). Never touches ``A:\\informe mensual`` (the real corpus is off-limits
for this round, per the plan's "Samples only" rule) or ``data/overseer.db``.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz
from PIL import Image

from core.scanners.patterns import CRS_RCH_ANCHORS
from core.scanners.utils.header_band_anchors import _normalize_text
from core.scanners.utils.ocr_backend import ocr_image
from core.scanners.utils.pagination_count import extract_code, parse_pagination

logger = logging.getLogger(__name__)

# Mirrors pagination_count._OCR_DPI (216) — same rendering resolution as production.
_OCR_DPI = 216
_MAX_PAGES = 50  # cap per sample (spec: "cap survey/benchmark page counts sensibly")

REGIONS: dict[str, tuple[float, float, float, float]] = {
    "current": (0.50, 0.0, 1.0, 0.15),  # production pagination_count._CORNER_PORTRAIT
    "amplified": (0.35, 0.0, 1.0, 0.20),
    "top_left_half": (0.0, 0.0, 0.5, 0.20),
}

# gt_key (eval/fixtures/ground_truth.json) -> filename under data/samples/.
# The 7 charla samples named explicitly in the Track D plan (Task 5 Step 2).
CHARLA_SAMPLES: dict[str, str] = {
    "CHAR_17": "CHAR_17.PDF",
    "CHAR_25": "CHAR_25.pdf",
    "CH_9": "CH_9.pdf",
    "CH_39": "CH_39.pdf",
    "CH_51": "CH_51docs.pdf",
    "CH_74": "CH_74docs.pdf",
    "CH_BSM_18": "CH_BSM_18.pdf",
}

_SAMPLES_DIR = Path(__file__).parent.parent.parent / "data" / "samples"
_GT_PATH = Path(__file__).parent.parent / "fixtures" / "ground_truth.json"
_RESULTS_DIR = Path(__file__).parent / "results"


@dataclass(frozen=True)
class PageSurveyRow:
    sample: str
    page_idx: int  # 0-based
    region: str
    raw: str
    curr: int | None
    total: int | None
    code: str | None
    matched_anchors: list[str]


def _region_text(page: fitz.Page, bbox: tuple[float, float, float, float]) -> str:
    r = page.rect
    clip = fitz.Rect(
        r.x0 + bbox[0] * r.width,
        r.y0 + bbox[1] * r.height,
        r.x0 + bbox[2] * r.width,
        r.y0 + bbox[3] * r.height,
    )
    pix = page.get_pixmap(
        matrix=fitz.Matrix(_OCR_DPI / 72.0, _OCR_DPI / 72.0), clip=clip, alpha=False
    )
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    return ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng").strip()


def survey_pdf(pdf_path: Path, *, max_pages: int = _MAX_PAGES) -> list[PageSurveyRow]:
    """OCR every (page, region) pair of *pdf_path* (capped at *max_pages*)."""
    rows: list[PageSurveyRow] = []
    with fitz.open(pdf_path) as doc:
        n = min(doc.page_count, max_pages)
        for pi in range(n):
            page = doc[pi]
            for region_name, bbox in REGIONS.items():
                raw = _region_text(page, bbox)
                curr, total = parse_pagination(raw)
                code = extract_code(raw)
                norm = _normalize_text(raw)
                matched = [a for a in CRS_RCH_ANCHORS if _normalize_text(a) in norm]
                rows.append(
                    PageSurveyRow(
                        sample=pdf_path.name,
                        page_idx=pi,
                        region=region_name,
                        raw=raw,
                        curr=curr,
                        total=total,
                        code=code,
                        matched_anchors=matched,
                    )
                )
    return rows


def homogeneous_period(pages_surveyed_total: int, gt_docs: int) -> int | None:
    """Pages-per-doc N iff *pages_surveyed_total* (the FULL pdf, not the capped
    survey) is an exact multiple of *gt_docs* and N > 1 — otherwise None (no
    reliable page-level cover/continuation label can be derived).
    """
    if gt_docs <= 0 or pages_surveyed_total % gt_docs != 0:
        return None
    n = pages_surveyed_total // gt_docs
    return n if n > 1 else None


def sample_summary(rows: list[PageSurveyRow], *, full_pages: int, gt_docs: int) -> dict:
    """Aggregate stats for one sample: pattern uniformity + per-region discriminator rates."""
    current_rows = [r for r in rows if r.region == "current"]
    curr1 = sum(1 for r in current_rows if r.curr == 1)
    totals = [r.total for r in current_rows if r.total]
    dominant = max(set(totals), key=totals.count) if totals else None
    codes_seen = sorted({r.code for r in current_rows if r.code})

    period = homogeneous_period(full_pages, gt_docs)
    per_region: dict[str, dict] = {}
    if period is not None:
        for region_name in REGIONS:
            region_rows = [r for r in rows if r.region == region_name]
            covers = [r for r in region_rows if r.page_idx % period == 0]
            continuations = [r for r in region_rows if r.page_idx % period != 0]
            cover_hit = sum(1 for r in covers if len(r.matched_anchors) >= 2)
            cont_fp = sum(1 for r in continuations if len(r.matched_anchors) >= 2)
            per_region[region_name] = {
                "cover_pages": len(covers),
                "cover_hit_rate_ge2": (cover_hit / len(covers)) if covers else None,
                "continuation_pages": len(continuations),
                "continuation_false_positive_rate_ge2": (
                    (cont_fp / len(continuations)) if continuations else None
                ),
            }

    return {
        "pages_surveyed": len(current_rows),
        "pages_total": full_pages,
        "gt_docs": gt_docs,
        "homogeneous_period": period,
        "pages_curr_eq_1": curr1,
        "apparent_overcount_ratio": (curr1 / gt_docs) if gt_docs else None,
        "dominant_total": dominant,
        "codes_seen": codes_seen,
        "per_region": per_region,
    }


def run_survey(samples: dict[str, str] = CHARLA_SAMPLES) -> dict:
    """Survey every sample in *samples*; return {gt_key: {"rows": [...], "summary": {...}}}."""
    gt = json.loads(_GT_PATH.read_text(encoding="utf-8"))
    out: dict = {}
    for gt_key, filename in samples.items():
        pdf_path = _SAMPLES_DIR / filename
        if not pdf_path.exists():
            logger.warning("SKIP %s — file not found: %s", gt_key, pdf_path)
            continue
        with fitz.open(pdf_path) as doc:
            full_pages = doc.page_count
        gt_docs = gt.get(gt_key, {}).get("doc_count")
        if gt_docs is None:
            logger.warning("SKIP %s — no ground_truth.json entry", gt_key)
            continue
        logger.info(
            "surveying %s (%s, %d pages, gt_docs=%d)…", gt_key, filename, full_pages, gt_docs
        )
        rows = survey_pdf(pdf_path)
        summary = sample_summary(rows, full_pages=full_pages, gt_docs=gt_docs)
        out[gt_key] = {"rows": rows, "summary": summary}
        logger.info(
            "  surveyed=%d/%d  curr==1: %d  overcount~=%.2fx  period=%s  codes=%s",
            summary["pages_surveyed"],
            summary["pages_total"],
            summary["pages_curr_eq_1"],
            summary["apparent_overcount_ratio"] or 0.0,
            summary["homogeneous_period"],
            summary["codes_seen"],
        )
    return out


def main() -> None:
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )

    results = run_survey()

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dump = {
        gt_key: {
            "rows": [asdict(r) for r in data["rows"]],
            "summary": data["summary"],
        }
        for gt_key, data in results.items()
    }
    out_path = _RESULTS_DIR / "rch_survey.json"
    out_path.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {sum(len(d['rows']) for d in results.values())} page-region rows -> {out_path}")

    print("\n=== Per-sample summary ===")
    for gt_key, data in results.items():
        s = data["summary"]
        print(
            f"{gt_key}: pages={s['pages_surveyed']}/{s['pages_total']} gt_docs={s['gt_docs']} "
            f"period={s['homogeneous_period']} curr==1:{s['pages_curr_eq_1']} "
            f"overcount~={s['apparent_overcount_ratio']:.2f}x dominant_total={s['dominant_total']} "
            f"codes={s['codes_seen']}"
        )
        if s["per_region"]:
            for region_name, r in s["per_region"].items():
                chr_rate = r["cover_hit_rate_ge2"]
                fp_rate = r["continuation_false_positive_rate_ge2"]
                print(
                    f"    {region_name:15s} cover_hit>=2anchors="
                    f"{chr_rate:.0%} ({r['cover_pages']}pp)  "
                    f"continuation_false_positive>=2anchors={fp_rate:.0%} ({r['continuation_pages']}pp)"
                    if chr_rate is not None and fp_rate is not None
                    else f"    {region_name:15s} (no labeled pages)"
                )


if __name__ == "__main__":
    main()
