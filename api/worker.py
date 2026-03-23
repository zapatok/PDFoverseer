import time
import logging
import fitz
from pathlib import Path

from api.state import session_manager
from api.websocket import _emit
from api.database import save_reads, get_reads, has_reads
from core import analyze_pdf, _build_documents, _CORE_HASH

logger = logging.getLogger("pdfoverserver")

def _recalculate_metrics(session_id: str):
    s = session_manager.get_or_create(session_id)
    
    total_docs = 0
    total_complete = 0
    total_incomplete = 0
    total_inferred = 0

    skipped_paths = s.skipped_pdfs
    
    for path, metrics in s.individual_metrics.items():
        if path in skipped_paths:
            continue
        total_docs += metrics.get("docs", 0)
        total_complete += metrics.get("complete", 0)
        total_incomplete += metrics.get("incomplete", 0)
        total_inferred += metrics.get("inferred", 0)
        
    s.total_docs = total_docs
    s.total_complete = total_complete
    s.total_incomplete = total_incomplete
    s.total_inferred = total_inferred
    
    _emit(session_id, "metrics", {
        "docs": s.total_docs,
        "complete": s.total_complete,
        "incomplete": s.total_incomplete,
        "inferred": s.total_inferred,
        "confidences": s.confidences,
        "individual": s.individual_metrics
    })


def _process_pdfs(session_id: str, start_index: int = 0):
    s = session_manager.get_or_create(session_id)
    _emit(session_id, "log", {"msg": "Pre-calculando páginas del lote...", "level": "info"})
    try:
        total_pages = 0
        done_pages = 0
        for i, pdf_path in enumerate(s.pdf_list):
            p_str = str(pdf_path)
            
            if has_reads(session_id, p_str):
                continue

            num_pages = s.page_counts.get(p_str)
            if num_pages is None:
                doc = fitz.open(p_str)
                num_pages = len(doc)
                s.page_counts[p_str] = num_pages
                doc.close()
            total_pages += num_pages
            if i < start_index:
                done_pages += num_pages
            
        s.global_total_pages = total_pages
        s.global_done_pages = done_pages
        _emit(session_id, "global_progress", {"done": done_pages, "total": total_pages, "elapsed": 0.0, "eta": 0.0})
        _emit(session_id, "log", {"msg": f"Total a procesar: {total_pages} páginas.", "level": "success"})
    except Exception as e:
        _emit(session_id, "log", {"msg": f"Error calculando páginas: {e}", "level": "error"})
        return

    _emit(session_id, "log", {"msg": "Iniciando análisis profundo...", "level": "section"})
    
    s.start_time = time.time()
    last_metrics_refresh = 0

    for idx in range(start_index, len(s.pdf_list)):
        pdf_path = s.pdf_list[idx]
        p_str = str(pdf_path)
        
        if has_reads(session_id, p_str):
            _emit(session_id, "log", {"msg": f"\n⏭ Omitiendo {pdf_path.name} (Ya procesado al 100%).", "level": "warn"})
            _emit(session_id, "status_update", {"idx": idx, "status": "done"})
            continue
            
        if s.skip_current:
            s.skip_current = False
            s.skipped_pdfs.add(p_str)
            _emit(session_id, "status_update", {"idx": idx, "status": "skipped"})
            continue
            
        if s.stop_requested:
            _emit(session_id, "status_update", {"idx": idx, "status": "error"})
            break
            
        _emit(session_id, "status_update", {"idx": idx, "status": "processing"})
        _emit(session_id, "log", {"msg": f"\n📄 [{idx+1}/{len(s.pdf_list)}] {pdf_path.name}", "level": "file_hdr"})
        
        def on_progress(done, total):
            with s._lock:
                s.global_done_pages += 1
            
            elapsed_raw = time.time() - s.start_time if s.start_time > 0 else 0
            active_pause = (time.time() - s.pause_start_time) if s.pause_start_time > 0 else 0
            elapsed = max(0.0, elapsed_raw - s.total_paused_time - active_pause)
            
            eta = 0
            if elapsed > 0 and (s.global_done_pages - done_pages) > 0:
                pages_per_seg = (s.global_done_pages - done_pages) / elapsed
                missing_pages = s.global_total_pages - s.global_done_pages
                eta = missing_pages / pages_per_seg if pages_per_seg > 0 else 0
                
            _emit(session_id, "file_progress", {"done": done, "total": total, "filename": pdf_path.name})
            _emit(session_id, "global_progress", {
                "done": s.global_done_pages, 
                "total": s.global_total_pages,
                "elapsed": elapsed,
                "eta": eta,
                "paused": not s.pause_event.is_set()
            })
            
            nonlocal last_metrics_refresh
            now = time.time()
            if now - last_metrics_refresh > 1.0 and s._metrics_dirty:
                _recalculate_metrics(session_id)
                s._metrics_dirty = False
                last_metrics_refresh = now
            
        def on_log(msg, level="info"):
            _emit(session_id, "log", {"msg": msg, "level": level})
            
        def on_issue(page, kind, detail, pil_img):
            with s._lock:
                issue = {
                    "id": s.issue_counter,
                    "pdf_path": p_str,
                    "filename": pdf_path.name,
                    "page": page,
                    "type": kind,
                    "detail": detail,
                    "impact": "sequence",
                }
                s.issue_counter += 1
                s.issues.append(issue)
                if len(s.issues) > 10_000:
                    s.issues = s.issues[-10_000:]
            _emit(session_id, "new_issue", issue)

        s.cancel_event.clear()
        
        try:
            docs, reads = analyze_pdf(
                p_str, 
                on_progress, 
                on_log,
                pause_event=s.pause_event,
                cancel_event=s.cancel_event,
                on_issue=on_issue,
                doc_mode="charla"
            )
            
            if s.stop_requested:
                on_log(f"Análisis abortado a petición del usuario. Extrayendo datos parciales...", "warn")
                break
            
            # Save to SQLite Buffer
            save_reads(session_id, p_str, reads)

            # Build documents and snapshot metrics immediately 
            valid_reads = [r for r in reads if r.method != "excluded"]
            if not valid_reads:
                s.confidences[p_str] = 1.0
            else:
                s.confidences[p_str] = sum(r.confidence for r in valid_reads) / len(valid_reads)
                
            _ud = _build_documents(reads, lambda m, l: None, lambda p, k, d, i=None: None)
            
            complete = [d for d in _ud if d.is_complete]
            incomplete = [d for d in _ud if not d.is_complete]
            inferred = sum(len(d.inferred_pages) for d in _ud)
            dir_docs = len([d for d in complete if not d.inferred_pages])
            inf_docs = len([d for d in complete if len(d.inferred_pages) > 0])
            
            s.individual_metrics[p_str] = {
                "docs": len(_ud),
                "complete": len(complete),
                "incomplete": len(incomplete),
                "inferred": inferred,
                "direct": dir_docs,
                "inferred_hi": inf_docs,
                "inferred_lo": 0
            }
            s._metrics_dirty = True

            _recalculate_metrics(session_id)

            try:
                _uo = sum(1 for d in _ud if d.is_complete)
                _ui = sum(len(d.inferred_pages) for d in _ud)
                on_log(
                    f"[UI:{_CORE_HASH}] {pdf_path.name} "
                    f"DOC:{len(_ud)} COM:{_uo} INC:{len(_ud)-_uo} INF:{_ui}",
                    "ai",
                )
            except Exception as _ui_err:
                on_log(f"[UI:ERR] {pdf_path.name} — {_ui_err!r}", "ai")
            
            if s.stop_requested:
                _emit(session_id, "status_update", {"idx": idx, "status": "error"})
                break
                
            if s.skip_current:
                s.skip_current = False
                _emit(session_id, "status_update", {"idx": idx, "status": "skipped"})
                continue
                
            _emit(session_id, "status_update", {"idx": idx, "status": "done"})
            
        except Exception as e:
            logger.exception("Error procesando %s", pdf_path.name)
            _emit(session_id, "log", {"msg": f"Error procesando {pdf_path.name}: {e}", "level": "error"})
            _emit(session_id, "status_update", {"idx": idx, "status": "error"})
            
        _emit(session_id, "global_progress", {"done": idx + 1, "total": len(s.pdf_list), "elapsed": time.time() - s.start_time, "eta": 0})
        
    s.running = False
    
    elapsed_total = time.time() - s.start_time if s.start_time > 0 else 0
    
    _emit(session_id, "process_finished", {
        "metrics": {
            "docs": s.total_docs,
            "complete": s.total_complete,
            "incomplete": s.total_incomplete,
            "inferred": s.total_inferred,
            "total_time": elapsed_total
        }
    })
    _emit(session_id, "log", {"msg": f"\n🏁 Proceso completado en {elapsed_total:.1f}s", "level": "ok"})
