import time
import logging
import fitz
from pathlib import Path

from api.state import state
from api.websocket import _emit
from core import analyze_pdf, _build_documents, _CORE_HASH

logger = logging.getLogger("pdfoverserver")

def _recalculate_metrics():
    # Recalculate the global metrics across all processed PDFs
    total_docs = 0
    total_complete = 0
    total_incomplete = 0
    total_inferred = 0

    # Snapshot under lock to avoid RuntimeError if worker modifies dict during iteration
    with state._lock:
        reads_snapshot = dict(state.pdf_reads)
    skipped_paths = state.skipped_pdfs

    for path, reads in reads_snapshot.items():
        if path in skipped_paths:
            continue
            
        # Rebuild docs purely to count them
        docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
        complete = [d for d in docs if d.is_complete]
        incomplete = [d for d in docs if not d.is_complete]
        inferred = sum(len(d.inferred_pages) for d in docs)
        
        total_docs += len(docs)
        total_complete += len(complete)
        total_incomplete += len(incomplete)
        total_inferred += inferred
        
    state.total_docs = total_docs
    state.total_complete = total_complete
    state.total_incomplete = total_incomplete
    state.total_inferred = total_inferred
    
    # Calculate PDF confidences and individual metrics (use same snapshot)
    pdf_confidences = {}
    pdf_metrics = {}
    for path, reads in reads_snapshot.items():
        if path in skipped_paths:
            pdf_confidences[path] = 0.0
            pdf_metrics[path] = {"docs": 0, "complete": 0, "incomplete": 0, "inferred": 0}
            continue
            
        valid_reads = [r for r in reads if r.method != "excluded"]
        if not valid_reads:
            pdf_confidences[path] = 1.0
        else:
            pdf_confidences[path] = sum(r.confidence for r in valid_reads) / len(valid_reads)
            
        docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
        complete = [d for d in docs if d.is_complete]
        incomplete = [d for d in docs if not d.is_complete]
        inferred = sum(len(d.inferred_pages) for d in docs)
        dir_docs = len([d for d in complete if not d.inferred_pages])
        inf_docs = len([d for d in complete if len(d.inferred_pages) > 0])
        pdf_metrics[path] = {
            "docs": len(docs),
            "complete": len(complete),
            "incomplete": len(incomplete),
            "inferred": inferred,
            "direct": dir_docs,
            "inferred_hi": inf_docs,
            "inferred_lo": 0
        }
            
    state.confidences = pdf_confidences
    
    _emit("metrics", {
        "docs": state.total_docs,
        "complete": state.total_complete,
        "incomplete": state.total_incomplete,
        "inferred": state.total_inferred,
        "confidences": state.confidences,
        "individual": pdf_metrics
    })


def _process_pdfs(start_index: int = 0):
    _emit("log", {"msg": "Pre-calculando páginas del lote...", "level": "info"})
    try:
        total_pages = 0
        done_pages = 0
        for i, pdf_path in enumerate(state.pdf_list):
            p_str = str(pdf_path)
            # Ignorar archivos 'done' de todo el pipeline 
            if p_str in state.pdf_reads:
                continue
                
            doc = fitz.open(p_str)
            num_pages = len(doc)
            total_pages += num_pages
            if i < start_index:
                done_pages += num_pages
            doc.close()
            
        state.global_total_pages = total_pages
        state.global_done_pages = done_pages
        _emit("global_progress", {"done": done_pages, "total": total_pages, "elapsed": 0.0, "eta": 0.0})
        _emit("log", {"msg": f"Total a procesar: {total_pages} páginas.", "level": "success"})
    except Exception as e:
        _emit("log", {"msg": f"Error calculando páginas: {e}", "level": "error"})
        return

    _emit("log", {"msg": "Iniciando análisis profundo...", "level": "section"})
    
    state.start_time = time.time()
    last_metrics_refresh = 0

    for idx in range(start_index, len(state.pdf_list)):
        pdf_path = state.pdf_list[idx]
        
        if str(pdf_path) in state.pdf_reads:
            _emit("log", {"msg": f"\n⏭ Omitiendo {pdf_path.name} (Ya procesado al 100%).", "level": "warn"})
            _emit("status_update", {"idx": idx, "status": "done"})
            continue
            
        if state.skip_current:
            state.skip_current = False
            state.skipped_pdfs.add(str(pdf_path))
            _emit("status_update", {"idx": idx, "status": "skipped"})
            continue
            
        if state.stop_requested:
            _emit("status_update", {"idx": idx, "status": "error"})
            break
            
        _emit("status_update", {"idx": idx, "status": "processing"})
        _emit("log", {"msg": f"\n📄 [{idx+1}/{len(state.pdf_list)}] {pdf_path.name}", "level": "file_hdr"})
        
        def on_progress(done, total):
            with state._lock:
                state.global_done_pages += 1
            
            elapsed_raw = time.time() - state.start_time if state.start_time > 0 else 0
            active_pause = (time.time() - state.pause_start_time) if state.pause_start_time > 0 else 0
            elapsed = max(0.0, elapsed_raw - state.total_paused_time - active_pause)
            
            eta = 0
            if elapsed > 0 and (state.global_done_pages - done_pages) > 0:
                pages_per_seg = (state.global_done_pages - done_pages) / elapsed
                missing_pages = state.global_total_pages - state.global_done_pages
                eta = missing_pages / pages_per_seg if pages_per_seg > 0 else 0
                
            _emit("file_progress", {"done": done, "total": total, "filename": pdf_path.name})
            _emit("global_progress", {
                "done": state.global_done_pages, 
                "total": state.global_total_pages,
                "elapsed": elapsed,
                "eta": eta,
                "paused": not state.pause_event.is_set()
            })
            
            # Periodically recalculate metrics live (every 5 pages approx to avoid UI lag)
            nonlocal last_metrics_refresh
            now = time.time()
            if now - last_metrics_refresh > 1.0:
                _recalculate_metrics()
                last_metrics_refresh = now
            
        def on_log(msg, level="info"):
            _emit("log", {"msg": msg, "level": level})
            
        def on_issue(page, kind, detail, pil_img):
            with state._lock:
                issue = {
                    "id": state.issue_counter,
                    "pdf_path": str(pdf_path),
                    "filename": pdf_path.name,
                    "page": page,
                    "type": kind,
                    "detail": detail,
                    "impact": "sequence",
                }
                state.issue_counter += 1
                state.issues.append(issue)
                if len(state.issues) > 10_000:
                    state.issues = state.issues[-10_000:]
            _emit("new_issue", issue)

        state.cancel_event.clear()
        
        try:
            docs, reads = analyze_pdf(
                str(pdf_path), 
                on_progress, 
                on_log,
                pause_event=state.pause_event,
                cancel_event=state.cancel_event,
                on_issue=on_issue,
                doc_mode="charla"
            )
            
            if state.stop_requested:
                on_log(f"Análisis abortado a petición del usuario. Extrayendo datos parciales...", "warn")
                break
            
            state.pdf_reads[str(pdf_path)] = reads

            _recalculate_metrics()

            # [UI:] line — actual UI counters after _recalculate_metrics rebuild
            try:
                _ud = _build_documents(reads, lambda m, l: None, lambda p, k, d, i=None: None)
                _uo = sum(1 for d in _ud if d.is_complete)
                _ui = sum(len(d.inferred_pages) for d in _ud)
                on_log(
                    f"[UI:{_CORE_HASH}] {pdf_path.name} "
                    f"DOC:{len(_ud)} COM:{_uo} INC:{len(_ud)-_uo} INF:{_ui}",
                    "ai",
                )
            except Exception as _ui_err:
                on_log(f"[UI:ERR] {pdf_path.name} — {_ui_err!r}", "ai")
            
            if state.stop_requested:
                _emit("status_update", {"idx": idx, "status": "error"})
                break
                
            if state.skip_current:
                state.skip_current = False
                _emit("status_update", {"idx": idx, "status": "skipped"})
                continue
                
            _emit("status_update", {"idx": idx, "status": "done"})
            
        except Exception as e:
            logger.exception("Error procesando %s", pdf_path.name)
            _emit("log", {"msg": f"Error procesando {pdf_path.name}: {e}", "level": "error"})
            _emit("status_update", {"idx": idx, "status": "error"})
            
        _emit("global_progress", {"done": idx + 1, "total": len(state.pdf_list), "elapsed": time.time() - state.start_time, "eta": 0})
        
    state.running = False
    
    elapsed_total = time.time() - state.start_time if state.start_time > 0 else 0
    
    _emit("process_finished", {
        "metrics": {
            "docs": state.total_docs,
            "complete": state.total_complete,
            "incomplete": state.total_incomplete,
            "inferred": state.total_inferred,
            "total_time": elapsed_total
        }
    })
    _emit("log", {"msg": f"\n🏁 Proceso completado en {elapsed_total:.1f}s", "level": "ok"})
