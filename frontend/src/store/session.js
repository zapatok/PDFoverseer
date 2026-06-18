import { create } from "zustand";
import { toast } from "sonner";
import { api } from "../lib/api";
import { createWSClient } from "../lib/ws";
import { invalidateHistory } from "../lib/useHistoryStore";
import { OCR_CONFIRM_PDF_THRESHOLD } from "../lib/constants";
import { estimateScanSeconds, shouldConfirmScan, totalPdfsForPairs } from "../lib/scanCost";
import { isCellReady } from "../lib/cell-status";
import { countTypeFor } from "../lib/sigla-info";

export const useSessionStore = create((set, get) => ({
  view: "month",
  hospital: null,
  hospitalMode: "scanned",
  focusSigla: null,
  months: [],
  session: null,
  loading: false,
  error: null,
  historyView: false,
  historyDrawer: null,   // { hospital, sigla } | null — drill-in del SparkGrid

  // FASE 2 additions
  scanningCells: new Set(),            // "HPV|odi" strings, mirrored in CategoryRow
  scanProgress: null,                  // {done, total, pdfName?, etaMs?, unit?, terminal?} | null
  filesTick: {},                       // "HPV|odi" → counter; bumped on cell_done so FileList/lightbox re-fetch per_file (G3)
  fileScan: null,                      // {hospital, sigla, filename, page, pagesTotal, terminal} | null — single-file OCR (rev-2 #1)
  lightbox: null,                      // {hospital, sigla, fileIndex, mode} | null
  _ws: null,

  // FASE 3 — pending-save coordination (see spec §6.6).
  // Map keyed by `${hospital}|${sigla}` → { controller: AbortController, status: 'saving' }
  _pendingSave: new Map(),
  // Public read view for components — keyed identically. Values: 'saving' | 'saved' | 'error'.
  pendingSaves: {},

  setView: (view) => set({
    view,
    ...(view !== "hospital" && { hospitalMode: "scanned", focusSigla: null }),
  }),

  toggleHistoryView: () => set((s) => ({ historyView: !s.historyView, historyDrawer: null })),
  setHistoryView: (v) => set({ historyView: !!v, historyDrawer: null }),

  openHistoryDrawer: (hospital, sigla) => set({ historyDrawer: { hospital, sigla } }),
  closeHistoryDrawer: () => set({ historyDrawer: null }),

  loadMonths: async () => {
    set({ loading: true, error: null });
    try {
      const { months } = await api.listMonths();
      set({ months, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  openMonth: async (sessionId, year, month) => {
    set({ loading: true, error: null });
    try {
      await api.createSession(year, month);
      const session = await api.getSession(sessionId);
      // Tear down any prior WS and reconnect for the new session
      get()._ws?.close();
      const ws = createWSClient(sessionId, { onEvent: get()._handleWSEvent });
      set({ session, loading: false, _ws: ws, scanningCells: new Set(), scanProgress: null, historyDrawer: null });
      if (Object.keys(session.cells || {}).length === 0) {
        // pase 1 only the first time the month is opened (spec §7); fire-and-forget,
        // runScan owns `loading`. Re-opening a scanned month never re-scans (it would
        // wipe OCR/per-file results).
        get().runScan(sessionId).catch((e) => console.error(e));
      }
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  selectHospital: (hospital, opts = {}) => set({
    view: "hospital",
    hospital,
    hospitalMode: opts.mode ?? "scanned",
    focusSigla: opts.focus ?? null,
  }),

  runScan: async (sessionId) => {
    set({ loading: true, error: null });
    try {
      await api.scanSession(sessionId);
      const session = await api.getSession(sessionId);
      set({ session, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  scanOcr: async (sessionId, cellPairs) => {
    // Cost guard (audit #2): warn before a long OCR run and remind that
    // regime-1 cells are already counted by filename. Estimated from the
    // pase-1 filename counts the client already holds.
    const totalPdfs = totalPdfsForPairs(get().session, cellPairs);
    if (shouldConfirmScan(totalPdfs, OCR_CONFIRM_PDF_THRESHOLD)) {
      const mins = Math.max(1, Math.round(estimateScanSeconds(totalPdfs) / 60));
      const ok = window.confirm(
        `Vas a escanear con OCR ${totalPdfs} PDFs (~${mins} min). En categorías ` +
          `de régimen 1 el conteo por nombre de archivo ya suele ser correcto. ¿Continuar?`,
      );
      if (!ok) return;
    }
    try {
      const resp = await api.scanOcr(sessionId, cellPairs);
      // Size the bar from the real PDF count (audit #1); scan_started will
      // confirm it over the WS moments later.
      set({ scanProgress: { done: 0, total: resp?.total_pdfs ?? 0, unit: "pdf" } });
    } catch (error) {
      set({ error: String(error) });
    }
  },

  // rev-2 #1 — OCR-scan a single file of a cell. Progress (file_*) + the merge
  // arrive over the WS; this just kicks it off.
  scanFileOcr: async (sessionId, hospital, sigla, filename) => {
    try {
      await api.scanFileOcr(sessionId, hospital, sigla, filename);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  // E5 — clear near-match suspects for a cell. `entry` = { pdf_name, page_index }
  // drops one; omit it to clear all. Optimistic, then persists.
  clearNearMatches: async (sessionId, hospital, sigla, entry) => {
    set((prev) => {
      const session = prev.session;
      const cell = session?.cells?.[hospital]?.[sigla];
      if (!cell) return {};
      const list = cell.near_matches || [];
      const nextList = entry
        ? list.filter(
            (nm) => !(nm.pdf_name === entry.pdf_name && nm.page_index === entry.page_index),
          )
        : [];
      const cells = { ...session.cells };
      const hosp = { ...cells[hospital] };
      hosp[sigla] = { ...cell, near_matches: nextList };
      cells[hospital] = hosp;
      return { session: { ...session, cells } };
    });
    try {
      await api.clearNearMatches(sessionId, hospital, sigla, entry);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  // Scan only the pendiente (amber) cells of a hospital with OCR. Reuses
  // scanOcr (and its cost guard) — never duplicates the threshold.
  scanPending: (sessionId, hospital) => {
    const cells = get().session?.cells?.[hospital] || {};
    const pairs = Object.keys(cells)
      .filter((sigla) => !isCellReady(cells[sigla], countTypeFor(sigla)))
      .map((sigla) => [hospital, sigla]);
    if (pairs.length === 0) return undefined;
    return get().scanOcr(sessionId, pairs);
  },

  cancelScan: async (sessionId) => {
    try { await api.cancelScan(sessionId); }
    catch (error) { set({ error: String(error) }); }
  },

  // Incr 2 — apply ratio N to all Pendiente files in a cell, then refresh.
  applyRatioCell: async (sessionId, hospital, sigla, n) => {
    try {
      const updatedCell = await api.applyRatio(sessionId, hospital, sigla, n);
      const tickKey = `${hospital}|${sigla}`;
      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = { ...hosp[sigla], ...updatedCell };
        cells[hospital] = hosp;
        return {
          session: { ...prev.session, cells },
          filesTick: { ...prev.filesTick, [tickKey]: (prev.filesTick[tickKey] ?? 0) + 1 },
        };
      });
    } catch (error) {
      set({ error: String(error) });
      throw error; // re-throw so the caller can show a failure toast (don't claim success)
    }
  },

  saveOverride: async (sessionId, hospital, sigla, value, opts = {}) => {
    const key = `${hospital}|${sigla}`;
    const controller = new AbortController();

    // 1+2 combined in a functional set() so reads + writes happen atomically.
    // This prevents the stale-read race when two rapid calls overlap: both
    // would read state._pendingSave before either set()ted, and both would
    // think they are 'first'. Functional setState gives us the prev state
    // synchronously inside the updater.
    set((prev) => {
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) {
        existing.controller.abort();
      }
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      return {
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });

    try {
      const result = await api.patchOverride(
        sessionId, hospital, sigla, value,
        { signal: controller.signal, manual: opts.manual },
      );

      // If our controller was aborted while in flight, the newer save wins.
      if (controller.signal.aborted) return;

      // Atomically patch session.cells + clear pending.
      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = {
          ...hosp[sigla],
          user_override: result.user_override,
        };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        // Only drop OUR controller — if a newer save raced in, leave it alone.
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          session: { ...prev.session, cells },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });

      // Auto-flush 'saved' state after 2s — but only if status is still
      // 'saved' (not overwritten by a newer 'saving' from another commit).
      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
      });
    }
  },

  savePerFileOverride: async (sessionId, hospital, sigla, filename, count) => {
    const key = `${hospital}|${sigla}|${filename}`;
    const controller = new AbortController();

    set((prev) => {
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) existing.controller.abort();
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      return {
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });

    try {
      const result = await api.patchPerFileOverride(
        sessionId, hospital, sigla, filename, count,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;

      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = {
          ...hosp[sigla],
          per_file_overrides: {
            ...(hosp[sigla]?.per_file_overrides ?? {}),
            [filename]: count,
          },
          count: result.new_cell_count,
        };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        // Bump filesTick so the FileList + lightbox re-fetch this cell and show
        // the new per-file count + the Manual chip for the edited file (Bug C).
        const tickKey = `${hospital}|${sigla}`;
        return {
          session: { ...prev.session, cells },
          filesTick: { ...prev.filesTick, [tickKey]: (prev.filesTick[tickKey] ?? 0) + 1 },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });

      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
      });
    }
  },

  confirmCell: async (sessionId, hospital, sigla, confirmed) => {
    const key = `${hospital}|${sigla}|confirm`;
    const controller = new AbortController();

    // Optimistic: flip the flag now so the dot turns listo/pendiente instantly
    // (matters for the "Marcar seleccionadas como listas" bulk action).
    set((prev) => {
      if (!prev.session) return {};
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) existing.controller.abort();
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      const cells = { ...prev.session.cells };
      const hosp = { ...cells[hospital] };
      hosp[sigla] = { ...hosp[sigla], confirmed };
      cells[hospital] = hosp;
      return {
        session: { ...prev.session, cells },
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });

    try {
      const result = await api.patchConfirm(
        sessionId, hospital, sigla, confirmed, { signal: controller.signal },
      );
      if (controller.signal.aborted) return;

      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = { ...hosp[sigla], confirmed: result.confirmed };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          session: { ...prev.session, cells },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });

      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      // Revert the optimistic flag on failure.
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        const next = {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
        if (prev.session) {
          const cells = { ...prev.session.cells };
          const hosp = { ...cells[hospital] };
          hosp[sigla] = { ...hosp[sigla], confirmed: !confirmed };
          cells[hospital] = hosp;
          next.session = { ...prev.session, cells };
        }
        return next;
      });
    }
  },

  saveWorkerCount: async (sessionId, hospital, sigla, patch) => {
    const key = `${hospital}|${sigla}|workers`;
    const controller = new AbortController();

    set((prev) => {
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) existing.controller.abort();
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      return {
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });

    try {
      const result = await api.patchWorkerCount(
        sessionId, hospital, sigla, patch, { signal: controller.signal },
      );
      if (controller.signal.aborted) return;

      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = {
          ...hosp[sigla],
          worker_marks: result.worker_marks,
          worker_status: result.worker_status,
          worker_cursor: result.worker_cursor,
          worker_count: result.worker_count,
        };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          session: { ...prev.session, cells },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });

      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
      });
    }
  },

  saveNote: async (sessionId, hospital, sigla, patch) => {
    const key = `${hospital}|${sigla}|note`;
    const controller = new AbortController();

    set((prev) => {
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) existing.controller.abort();
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      return {
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });

    try {
      const result = await api.patchNote(
        sessionId, hospital, sigla, patch, { signal: controller.signal },
      );
      if (controller.signal.aborted) return;

      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = {
          ...hosp[sigla],
          note: result.note,
          note_status: result.note_status,
          // Backend recomputes all_reliable after the note gate (por_resolver →
          // not settled); merge it so the stored field doesn't drift on resolve.
          all_reliable: result.all_reliable,
        };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          session: { ...prev.session, cells },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });

      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
      });
    }
  },

  // Incr J — reorg ops. All three re-fetch the full session on success so that
  // the backend-recomputed reorg_doc_delta/reorg_worker_delta across all cells
  // is reflected consistently (client merge would be error-prone here).
  addReorgOp: async (sessionId, hospital, sigla, opDraft) => {
    try {
      await api.createReorgOp(sessionId, {
        source: { hospital, sigla, ...opDraft.source },
        dest: opDraft.dest,
        op_type: opDraft.op_type,
        empresa: opDraft.empresa,
        preserve_date: opDraft.preserve_date,
        rotation_deg: opDraft.rotation_deg,
        doc_count: opDraft.doc_count,
        worker_count: opDraft.worker_count,
        note: opDraft.note,
      });
      const session = await api.getSession(sessionId);
      set({ session });
    } catch (error) {
      toast.error(`No se pudo crear la operación: ${String(error)}`);
      throw error;
    }
  },

  deleteReorgOp: async (sessionId, opId) => {
    try {
      await api.deleteReorgOp(sessionId, opId);
      const session = await api.getSession(sessionId);
      set({ session });
    } catch (error) {
      toast.error(`No se pudo eliminar la operación: ${String(error)}`);
      throw error;
    }
  },

  exportManifest: async (sessionId) => {
    try {
      const result = await api.exportManifest(sessionId);
      toast.success(`Manifiesto exportado — ${result.operation_count} operación(es)`);
      return result;
    } catch (error) {
      toast.error(`No se pudo exportar el manifiesto: ${String(error)}`);
      throw error;
    }
  },

  openLightbox: (hospital, sigla, fileIndex = 0, mode = "inspect") =>
    set({ lightbox: { hospital, sigla, fileIndex, mode } }),
  closeLightbox: () => set({ lightbox: null }),

  openWorkerCount: (hospital, sigla) => {
    const cell = get().session?.cells?.[hospital]?.[sigla];
    set({
      lightbox: {
        hospital,
        sigla,
        fileIndex: cell?.worker_cursor?.file ?? 0,
        mode: "count_workers",
      },
    });
  },

  generateOutput: async (sessionId) => {
    set({ loading: true, error: null });
    try {
      const result = await api.generateOutput(sessionId);
      set({ loading: false });
      invalidateHistory(sessionId);
      return result;
    } catch (error) {
      set({ error: String(error), loading: false });
      throw error;
    }
  },

  // M1 multiplayer — re-fetch the full session from the server (used by
  // session_refresh WS event, WS reconnect, and tab refocus auto-heal).
  refetchSession: async (sessionId) => {
    try {
      const session = await api.getSession(sessionId);
      set({ session });
    } catch (error) {
      console.error("refetchSession failed", error);
    }
  },

  // ---------- WS event handler ----------
  _handleWSEvent: (event) => {
    const state = get();
    const cellKey = (h, s) => `${h}|${s}`;

    switch (event.type) {
      case "cell_scanning": {
        const next = new Set(state.scanningCells);
        next.add(cellKey(event.hospital, event.sigla));
        set({ scanningCells: next });
        break;
      }
      case "cell_done": {
        const next = new Set(state.scanningCells);
        next.delete(cellKey(event.hospital, event.sigla));
        // Bump filesTick: this event just wrote fresh per_file to the DB, so
        // FileList + lightbox must re-fetch to show the new chip + count (G3,
        // review #5/#6). Key matches the cellKey/subscription format.
        const tickKey = cellKey(event.hospital, event.sigla);
        const filesTick = {
          ...state.filesTick,
          [tickKey]: (state.filesTick[tickKey] ?? 0) + 1,
        };
        const session = state.session;
        if (session) {
          const cells = { ...session.cells };
          const hosp = { ...cells[event.hospital] };
          hosp[event.sigla] = {
            ...hosp[event.sigla],
            ocr_count: event.result.ocr_count,
            method: event.result.method,
            confidence: event.result.confidence,
            duration_ms_ocr: event.result.duration_ms_ocr,
            near_matches: event.result.near_matches ?? [],
            // Keep per_file fresh so the DetailPanel can locate a near-match's
            // PDF (Bug B) and computeCellCount reflects the OCR per-file counts.
            per_file: event.result.per_file ?? hosp[event.sigla]?.per_file ?? {},
          };
          cells[event.hospital] = hosp;
          set({ scanningCells: next, session: { ...session, cells }, filesTick });
        } else {
          set({ scanningCells: next, filesTick });
        }
        break;
      }
      case "cell_updated": {
        const session = state.session;
        if (!session) break;
        const cells = { ...session.cells };
        const hosp = { ...(cells[event.hospital] || {}) };
        hosp[event.sigla] = event.cell;           // reemplazo de celda COMPLETA (§4)
        cells[event.hospital] = hosp;
        const tickKey = cellKey(event.hospital, event.sigla);
        const filesTick = {
          ...state.filesTick,
          [tickKey]: (state.filesTick[tickKey] ?? 0) + 1,
        };
        set({ session: { ...session, cells }, filesTick });
        break;
      }
      case "cell_error": {
        const next = new Set(state.scanningCells);
        next.delete(cellKey(event.hospital, event.sigla));
        const session = state.session;
        if (session) {
          const cells = { ...session.cells };
          const hosp = { ...cells[event.hospital] };
          const prev = hosp[event.sigla] || {};
          hosp[event.sigla] = { ...prev, errors: [...(prev.errors || []), event.error] };
          cells[event.hospital] = hosp;
          set({ scanningCells: next, session: { ...session, cells } });
        } else {
          set({ scanningCells: next });
        }
        break;
      }
      case "scan_started":
        // Real denominator for the bar: number of PDFs to scan (audit #1).
        set({ scanProgress: { done: 0, total: event.total_pdfs, unit: "pdf" } });
        break;
      case "pdf_progress":
        set({
          scanProgress: {
            done: event.done,
            total: event.total,
            pdfName: event.pdf_name,
            etaMs: event.eta_ms,
            unit: "pdf",
          },
        });
        break;
      case "scan_progress":
        // Legacy cell-granularity progress — superseded by pdf_progress
        // (audit #1). Still emitted by the backend for test/compat reasons;
        // ignored here so it doesn't fight the per-PDF bar.
        break;
      case "scan_complete":
        // Scan run terminated → no cell can still be scanning. Defensive:
        // clears any cell that never emitted its own cell_done/cell_error.
        // Finalize the PDF bar at 100% without clobbering its denominator.
        set({
          scanningCells: new Set(),
          scanProgress: {
            ...state.scanProgress,
            terminal: "complete",
            done: state.scanProgress?.total ?? 0,
          },
        });
        // Auto-dismiss after 5s
        setTimeout(() => set((s) => (s.scanProgress?.terminal === "complete" ? { scanProgress: null } : s)), 5000);
        break;
      case "scan_cancelled":
        // Scan run terminated → clear scanningCells. The interrupted cell
        // never emits cell_done/cell_error; without this it stays stuck
        // on "Escaneando…" forever (bug caught in the FASE 5 smoke). Keep the
        // per-PDF done where it stopped; just mark the bar cancelled.
        set({
          scanningCells: new Set(),
          scanProgress: { ...state.scanProgress, terminal: "cancelled" },
        });
        setTimeout(() => set((s) => (s.scanProgress?.terminal === "cancelled" ? { scanProgress: null } : s)), 5000);
        break;
      // --- single-file OCR (rev-2 #1) ---
      case "file_scan_started":
        set({
          fileScan: {
            hospital: event.hospital,
            sigla: event.sigla,
            filename: event.filename,
            page: 0,
            pagesTotal: event.pages_total ?? 0,
            terminal: null,
          },
        });
        break;
      case "file_page_progress":
        set((s) =>
          s.fileScan && s.fileScan.filename === event.filename
            ? { fileScan: { ...s.fileScan, page: event.page, pagesTotal: event.pages_total ?? s.fileScan.pagesTotal } }
            : {},
        );
        break;
      case "file_scan_done": {
        // Backend merged this file's per_file → bump filesTick so the FileList +
        // lightbox re-fetch (mirror cell_done); mark the bar done, then dismiss.
        const fkey = `${event.hospital}|${event.sigla}`;
        set((s) => ({
          filesTick: { ...s.filesTick, [fkey]: (s.filesTick[fkey] ?? 0) + 1 },
          fileScan: s.fileScan ? { ...s.fileScan, terminal: "done" } : null,
        }));
        setTimeout(() => set((s) => (s.fileScan?.terminal === "done" ? { fileScan: null } : s)), 1500);
        break;
      }
      case "file_scan_error":
        set((s) => ({
          fileScan: s.fileScan ? { ...s.fileScan, terminal: "error" } : null,
          error: event.error ?? "Error al escanear el archivo",
        }));
        setTimeout(() => set((s) => (s.fileScan?.terminal === "error" ? { fileScan: null } : s)), 4000);
        break;
      case "session_refresh": {
        const sid = state.session?.session_id;
        if (sid) get().refetchSession(sid);
        break;
      }
      case "ping":
        break;     // keepalive — no-op
      default:
        // Unknown event types ignored
    }
  },
}));
