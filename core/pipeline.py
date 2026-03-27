"""Pipeline engine: producer-consumer orchestration and human-in-the-loop workflows."""
from __future__ import annotations

import hashlib
import threading
import time
from collections import Counter
from pathlib import Path

import fitz

import core.inference as inference
import core.ocr as ocr
from core.utils import (
    BATCH_SIZE,
    INFERENCE_ENGINE_VERSION,
    PAGE_PATTERN_VERSION,
    PARALLEL_WORKERS,
    Document,
    _PageRead,
)

_CUDA_HASH = hashlib.md5(b"CUDA-GPU-V4-Producer-Consumer").hexdigest()[:8]
_CORE_HASH = "2e436564"  # Commit from the last test that was shown to the user


# ── Process Pool Worker (Top-Level for Pickling) ──────────────────────────────

def _process_page_worker(pdf_path: str, page_idx: int) -> _PageRead:
    """Stateless worker function for true multiprocessing."""
    import fitz

    import core.ocr as ocr
    doc = fitz.open(pdf_path)
    try:
        return ocr._process_page(doc, page_idx)
    finally:
        doc.close()


# ── AI Telemetry ─────────────────────────────────────────────────────────────

def _emit_ai_telemetry(
    on_log: callable,
    pdf_path,
    documents: list[Document],
    reads_clean: list[_PageRead],
    period_info: dict,
    elapsed: float,
    total_pages: int,
    method_tally: dict,
) -> None:
    """Emit [AI:] and [DS:] compact telemetry blocks to the log.

    The [AI:] block (log level "ai") format:
        [AI:<core_hash>] [MOD:<version>] [CUDA:<hash>] [REG:<pattern_version>] <filename> | <pages>p <elapsed>s <ms/p>ms/p | W<workers> | INF:<engine_version>
        PRE5≡ DOC:<n_docs> COM:<complete>(<pct>) INC:<incomplete> INF:<inferred_count>
        OCR: direct:<n>,super_resolution:<n>,...
        DOCS: <total>total → <ok>ok+<bad_summary> | dist: <Np×count> ...
        INF: <total>total(low:<n> mid:<n> hi:<n>) | LOW: <page>=<curr>/<total>(<conf>)...
        FAIL: <n>pp:<page>,<page>,...

    The [DS:] block (log level "ai_inf") format:
        [DS:<core_hash>] D:<n_docs> P:P=<period> conf=<pct> expect=<total>
        INF:<n> x̄=<avg_conf> <consistent>✓<uncertain>~<conflicting>✗
        ✓<XVAL ok entries>    — format: <pdf_page>:<left_neighbor>><curr>/<total>@<conf%>><right_neighbor>
        ~<XVAL uncertain entries>
        ✗<XVAL bad entries>

    XVAL entry format: <pdf_page>:<left>><curr>/<total>@<conf%>><right>
        where left/right = "<curr>/<total><method_char>" and method chars are:
        d=direct, s=super_resolution, e=easyocr, i=inferred, f=failed, ?=unknown
    """
    fname = Path(pdf_path).name
    mstr = ",".join(f"{k}:{v}" for k, v in method_tally.items() if v)

    size_dist = Counter(d.declared_total for d in documents)
    dist_str = " ".join(f"{s}p×{c}" for s, c in sorted(size_dist.items()))

    docs_ok    = sum(1 for d in documents if d.is_complete)
    docs_bad   = len(documents) - docs_ok
    seq_broken = sum(1 for d in documents if not d.sequence_ok)
    undercount = sum(1 for d in documents if d.sequence_ok and not d.is_complete)
    bad_str = f"{docs_bad}bad(seq:{seq_broken} under:{undercount})" if docs_bad else "0bad"

    inf_reads = [r for r in reads_clean if r.method == "inferred"]
    inf_low   = [r for r in inf_reads if r.confidence < 0.50]
    inf_mid   = [r for r in inf_reads if 0.50 <= r.confidence <= 0.60]
    inf_high  = [r for r in inf_reads if r.confidence > 0.60]
    low_pages = [f"p{r.pdf_page}={r.curr}/{r.total}({r.confidence:.0%})" for r in inf_low[:8]]
    if len(inf_low) > 8:
        low_pages.append(f"...+{len(inf_low)-8}more")
    low_str = " ".join(low_pages) if low_pages else "none"

    failed_pp = [r.pdf_page for r in reads_clean if r.method == "failed"]
    fail_str = (
        f"{len(failed_pp)}pp:{','.join(map(str, failed_pp[:10]))}"
        f"{'...' if len(failed_pp) > 10 else ''}"
        if failed_pp else "none"
    )

    n_docs = len(documents)
    success_pct = f"{docs_ok/n_docs:.0%}" if n_docs else "n/a"

    on_log(
        f"[AI:{_CORE_HASH}] [MOD:v6-tess-sr] [CUDA:{_CUDA_HASH}] [REG:{PAGE_PATTERN_VERSION}] {fname} | {total_pages}p {elapsed:.1f}s {elapsed/total_pages*1000:.0f}ms/p"
        f" | W{PARALLEL_WORKERS} | INF:{INFERENCE_ENGINE_VERSION}\n"
        f"PRE5≡ DOC:{n_docs} COM:{docs_ok}({success_pct}) INC:{docs_bad} INF:{len(inf_reads)}\n"
        f"OCR: {mstr}\n"
        f"DOCS: {n_docs}total → {docs_ok}ok+{bad_str} | dist: {dist_str}\n"
        f"INF: {len(inf_reads)}total(low:{len(inf_low)} mid:{len(inf_mid)} hi:{len(inf_high)}) | LOW: {low_str}\n"
        f"FAIL: {fail_str}",
        "ai",
    )

    _p = period_info
    per_str = (
        f"P={_p['period']} conf={_p['confidence']:.0%} expect={_p['expected_total']}"
        if _p.get("period") else "none"
    )
    avg_inf_conf  = sum(r.confidence for r in inf_reads) / len(inf_reads) if inf_reads else 0.0
    n_consistent  = sum(1 for r in inf_reads if r.confidence >= 0.90)
    n_conflicting = sum(1 for r in inf_reads if r.confidence < 0.45)

    _M = {"direct": "d", "super_resolution": "s", "easyocr": "e", "inferred": "i", "failed": "f"}
    _rc = reads_clean

    def _nb(idx: int) -> str:
        if idx < 0 or idx >= len(_rc):
            return "-"
        r = _rc[idx]
        return f"{r.curr}/{r.total}{_M.get(r.method, '?')}"

    xv_ok, xv_unk, xv_bad = [], [], []
    for idx, r in enumerate(_rc):
        if r.method != "inferred":
            continue
        c = int(r.confidence * 100)
        entry = f"{r.pdf_page}:{_nb(idx-1)}>{r.curr}/{r.total}@{c}>{_nb(idx+1)}"
        if r.confidence >= 0.90:
            xv_ok.append(entry)
        elif r.confidence < 0.45:
            xv_bad.append(entry)
        else:
            xv_unk.append(entry)

    on_log(
        f"[DS:{_CORE_HASH}] D:{n_docs} P:{per_str}\n"
        f"INF:{len(inf_reads)} x̄={avg_inf_conf:.0%} "
        f"{n_consistent}✓{len(xv_unk)}~{n_conflicting}✗\n"
        f"✓{','.join(xv_ok) or '-'}\n"
        f"~{','.join(xv_unk) or '-'}\n"
        f"✗{','.join(xv_bad) or '-'}",
        "ai_inf",
    )


# ── Main analysis function ────────────────────────────────────────────────────

def analyze_pdf(
    pdf_path: str,
    on_progress: callable,
    on_log:      callable,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    on_issue:    callable | None = None,
    doc_mode:    str = "charla",
) -> tuple[list[Document], list[_PageRead]]:
    """Run the V4 OCR + inference pipeline on a PDF file.

    Spawns PARALLEL_WORKERS processes via ProcessPoolExecutor, each running
    Tesseract Tier 1 (direct) + Tier 2 (4x SR bicubic) on a page crop.
    Pages are processed in batches of BATCH_SIZE with pause/cancel support.

    After OCR, runs period detection (autocorrelation) and Dempster-Shafer
    inference to recover failed pages, then builds Document boundaries.

    Args:
        pdf_path:     Absolute path to the PDF file.
        on_progress:  Callback(pdf_page, total_pages) — called after each page.
        on_log:       Callback(message, level) — receives all log lines.
        pause_event:  If set, workers wait at batch boundaries. Default: None.
        cancel_event: If set and is_set(), scan aborts immediately. Default: None.
        on_issue:     Callback(page, kind, detail, extra) for low-confidence
                      inferences and other issues. Default: None.
        doc_mode:     Document mode string (currently unused, reserved). Default: "charla".

    Returns:
        Tuple of (documents, reads):
        - documents: List[Document] — inferred document boundaries.
        - reads: List[_PageRead] — one entry per page with OCR result and method.
        Returns ([], []) on PDF read error or cancel.
    """
    if not ocr._sr_initialized:
        ocr._setup_sr(on_log)

    on_log("Leyendo metadatos...", "info")
    try:
        meta_doc    = fitz.open(pdf_path)
        total_pages = len(meta_doc)
        meta_doc.close()
    except Exception as e:
        on_log(f"Error leyendo PDF: {e}", "error")
        return [], []

    on_log(f"Total paginas: {total_pages}", "info")
    on_log(
        f"Pipeline V4: Tesseract x{PARALLEL_WORKERS} producers + SR-GPU Tier 2 (batch={BATCH_SIZE})",
        "info",
    )

    def _issue(page: int, kind: str, detail: str):
        if on_issue is not None:
            on_issue(page, kind, detail, None)

    reads: list[_PageRead] = [None] * total_pages
    method_tally: dict[str, int] = {}
    t0 = time.time()

    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        for batch_start in range(0, total_pages, BATCH_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                on_log("Analisis abortado a peticion del usuario.", "warn")
                return [], []

            if pause_event is not None:
                pause_event.wait()

            batch_end = min(batch_start + BATCH_SIZE, total_pages)

            future_to_idx = {
                pool.submit(_process_page_worker, pdf_path, i): i
                for i in range(batch_start, batch_end)
            }

            batch_results: dict[int, _PageRead] = {}
            for future, i in future_to_idx.items():
                try:
                    batch_results[i] = future.result()
                except Exception as e:
                    pdf_page = i + 1
                    on_log(f"  Pag {pdf_page:>4}: error de procesamiento: {e}", "error")
                    batch_results[i] = _PageRead(pdf_page, None, None, "failed", 0.0)

            for i in range(batch_start, batch_end):
                r = batch_results[i]
                reads[i] = r
                method_tally[r.method] = method_tally.get(r.method, 0) + 1

                pdf_page = i + 1
                if r.curr is not None:
                    on_log(f"  Pag {pdf_page:>4}: {r.curr}/{r.total}  [{r.method}]", "page_ok")
                else:
                    on_log(f"  Pag {pdf_page:>4}: ???  [failed]", "page_warn")

                if on_progress:
                    on_progress(pdf_page, total_pages)

    reads_clean: list[_PageRead] = [r for r in reads if r is not None]
    period_info = inference._detect_period(reads_clean)
    if period_info["period"] is not None:
        on_log(
            f"Periodo detectado: {period_info['period']} pags/ciclo "
            f"(confianza: {period_info['confidence']:.0%}, "
            f"total esperado: {period_info['expected_total']})",
            "info",
        )

    failed_count = sum(1 for r in reads_clean if r.method == "failed")
    if failed_count > 0:
        on_log(f"Inferencia D-S: procesando {failed_count} paginas fallidas...", "info")
        reads_clean, _inf_issues = inference._infer_missing(reads_clean, period_info)
        inferred = sum(1 for r in reads_clean if r.method == "inferred")
        on_log(f"Inferencia: {inferred} paginas recuperadas", "ok")

    from collections import defaultdict as _dd
    inf_groups: dict = _dd(list)
    for r in reads_clean:
        if r.method == "inferred" and r.confidence <= 0.45:
            conf_label = "BAJA"
            key = (r.curr, r.total, conf_label, f"{r.confidence:.0%}")
            inf_groups[key].append(r.pdf_page)
            detail = (f"Pag {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail)
    for (curr, total, conf_label, conf_pct), pages in inf_groups.items():
        pages_str = ", ".join(map(str, pages))
        on_log(f"  -> inferida {curr}/{total} {conf_label}({conf_pct}): pags {pages_str}", "warn")

    documents = inference._build_documents(reads_clean, on_log, _issue, period_info)

    _tele_docs = inference._build_documents(reads_clean, lambda m, l: None, lambda p, k, d: None, period_info)

    reads_by_page = {r.pdf_page: r for r in reads_clean}
    _uc_fixed = 0
    for di in range(len(documents) - 1):
        d = documents[di]
        d_next = documents[di + 1]
        missing = d.declared_total - d.found_total
        if missing <= 0 or d.declared_total <= 1:
            continue
        if (d_next.found_total <= missing
                and d_next.declared_total == d.declared_total):
            next_pages = d_next.pages + d_next.inferred_pages
            has_confirmed_start = any(
                reads_by_page[pp].curr == 1
                and reads_by_page[pp].method not in ("inferred", "failed", "excluded")
                for pp in next_pages if pp in reads_by_page
            )
            if has_confirmed_start:
                continue
            # Intentional mutation: correcting undercount by merging next-doc pages into current-doc
            for pp in next_pages:
                r = reads_by_page.get(pp)
                if r and r.method == "inferred":
                    r.curr = d.found_total + 1
                    r.total = d.declared_total
                    r.confidence = min(r.confidence + 0.10, 0.85)
            d.inferred_pages.extend(next_pages)
            d_next.pages.clear()
            d_next.inferred_pages.clear()
            d_next.declared_total = 0
            _uc_fixed += 1
    if _uc_fixed:
        documents = [d for d in documents if d.declared_total > 0]
        for i, d in enumerate(documents):
            d.index = i + 1
        on_log(f"Recuperacion undercount: {_uc_fixed} docs completados", "ok")

    elapsed = time.time() - t0
    on_log(f"Metodos OCR: {method_tally}", "info")
    on_log(
        f"Tiempo: {elapsed:.1f}s ({total_pages} paginas, "
        f"{elapsed / total_pages * 1000:.0f}ms/pag promedio, "
        f"{PARALLEL_WORKERS} workers)",
        "info",
    )
    _emit_ai_telemetry(
        on_log=on_log,
        pdf_path=pdf_path,
        documents=_tele_docs,
        reads_clean=reads_clean,
        period_info=period_info,
        elapsed=elapsed,
        total_pages=total_pages,
        method_tally=method_tally,
    )
    on_log("Motor de inferencia: D-S v1 + deteccion de periodo", "section")

    return documents, reads_clean


def re_infer_documents(
    reads: list[_PageRead],
    corrections: dict[int, tuple[int, int]],
    on_log: callable,
    on_issue: callable | None = None,
    exclusions: list[int] | None = None,
) -> tuple[list[Document], list[_PageRead]]:
    """Re-run document inference applying manual corrections and exclusions.

    Used after the user corrects document boundaries in the UI. Mutates
    the provided reads in-place: corrections override (curr, total) with
    confidence=1.0; exclusions set method="excluded" and clear curr/total.

    Args:
        reads:       List[_PageRead] from a previous analyze_pdf() call.
        corrections: Dict mapping pdf_page → (curr, total) manual override.
        on_log:      Callback(message, level) — receives all log lines.
        on_issue:    Callback(page, kind, detail, extra) for new low-confidence
                     inferences post-correction. Default: None.
        exclusions:  List of pdf_page numbers to exclude from inference. Default: [].

    Returns:
        Tuple of (documents, reads):
        - documents: Re-inferred List[Document] after applying corrections.
        - reads: The same list, mutated in-place with corrections applied.
    """
    def _issue(page: int, kind: str, detail: str):
        if on_issue is not None:
            on_issue(page, kind, detail, None)

    if exclusions is None:
        exclusions = []

    for r in reads:
        if r.pdf_page in exclusions:
            r.method = "excluded"
            r.curr = None
            r.total = None
            r.confidence = 1.0
        elif r.pdf_page in corrections:
            curr, tot = corrections[r.pdf_page]
            r.curr = curr
            r.total = tot
            r.method = "manual"
            r.confidence = 1.0
        elif r.method == "inferred":
            r.method = "failed"
            r.curr = None
            r.total = None
            r.confidence = 0.0

    period_info = inference._detect_period(reads)
    reads, _issues = inference._infer_missing(reads, period_info)

    for r in reads:
        if r.method == "inferred" and r.confidence <= 0.45:
            conf_label = "BAJA"
            detail = (f"Pag {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            on_log(f"  -> {detail}", "warn")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail)

    documents = inference._build_documents(reads, on_log, _issue)

    return documents, reads
