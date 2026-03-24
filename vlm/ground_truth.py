"""Load ground truth and corpus entries from all_index.csv + eval fixtures."""
from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

OCR_ALL_DIR = Path("data/ocr_all")
ALL_INDEX = OCR_ALL_DIR / "all_index.csv"
FIXTURES_DIR = Path("eval/fixtures/real")

# Trusted methods from eval fixtures (NOT "inferred" or "failed")
_TRUSTED_METHODS = {"direct", "super_resolution", "easyocr"}


@dataclass
class CorpusEntry:
    pdf_nickname: str
    page_num: int
    tier1_parsed: str
    tier2_parsed: str
    image_path: str  # relative to OCR_ALL_DIR


def _parse_nm(s: str) -> tuple[int, int] | None:
    """Parse 'N/M' string into (curr, total)."""
    if not s or "/" not in s:
        return None
    parts = s.split("/")
    if len(parts) != 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def load_ground_truth() -> dict[tuple[str, int], tuple[int, int]]:
    """Build ground truth dict from CSV tier reads + eval fixtures.

    Returns {(pdf_nickname, page_num): (curr, total)}.
    Priority: CSV tier1/tier2 parsed reads first, then eval fixture reads
    (excluding inferred/failed methods).
    """
    gt: dict[tuple[str, int], tuple[int, int]] = {}

    # Source 1: CSV tier reads (highest priority — actual OCR results)
    with open(ALL_INDEX, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            nickname = row["pdf_nickname"]
            page = int(row["page_num"])
            key = (nickname, page)
            if key in gt:
                continue
            parsed = _parse_nm(row["tier1_parsed"]) or _parse_nm(row["tier2_parsed"])
            if parsed:
                gt[key] = parsed

    # Source 2: Eval fixtures (fill gaps with trusted OCR reads only)
    if FIXTURES_DIR.exists():
        for fpath in sorted(FIXTURES_DIR.glob("*.json")):
            data = json.loads(fpath.read_text(encoding="utf-8"))
            nickname = data["name"]
            for read in data["reads"]:
                if read["method"] not in _TRUSTED_METHODS:
                    continue
                key = (nickname, read["pdf_page"])
                if key in gt:
                    continue
                curr, total = read.get("curr"), read.get("total")
                if curr is not None and total is not None:
                    gt[key] = (curr, total)

    return gt


def load_corpus(
    failures_only: bool = True,
    sample_n: int | None = None,
    seed: int = 42,
) -> list[CorpusEntry]:
    """Load corpus entries from all_index.csv.

    Args:
        failures_only: If True, only return entries where both tier1 and tier2 failed.
        sample_n: If set, randomly sample N entries.
        seed: Random seed for sampling.
    """
    entries: list[CorpusEntry] = []
    with open(ALL_INDEX, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t1 = row["tier1_parsed"].strip()
            t2 = row["tier2_parsed"].strip()
            if failures_only and (t1 or t2):
                continue
            entries.append(CorpusEntry(
                pdf_nickname=row["pdf_nickname"],
                page_num=int(row["page_num"]),
                tier1_parsed=t1,
                tier2_parsed=t2,
                image_path=row["image_path"],
            ))

    if sample_n is not None and sample_n < len(entries):
        rng = random.Random(seed)
        entries = rng.sample(entries, sample_n)

    return entries
