import { create } from "zustand";
import { api } from "../lib/api";
import { createWSClient } from "../lib/ws";
import { invalidateHistory } from "../lib/useHistoryStore";
import { OCR_CONFIRM_PDF_THRESHOLD } from "../lib/constants";
import { estimateScanSeconds, shouldConfirmScan, totalPdfsForPairs } from "../lib/scanCost";

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

  cancelScan: async (sessionId) => {
    try { await api.cancelScan(sessionId); }
    catch (error) { set({ error: String(error) }); }
  },

  saveOverride: async (sessionId, hospital, sigla, value, note, opts = {}) => {
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
        sessionId, hospital, sigla, value, note,
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
          override_note: result.override_note,
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
          };
          cells[event.hospital] = hosp;
          set({ scanningCells: next, session: { ...session, cells } });
        } else {
          set({ scanningCells: next });
        }
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
      case "ping":
        break;     // keepalive — no-op
      default:
        // Unknown event types ignored
    }
  },
}));
