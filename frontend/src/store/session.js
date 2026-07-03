import { create } from "zustand";
import { toast } from "sonner";
import { api } from "../lib/api";
import { createWSClient } from "../lib/ws";
import { getIdentity, getParticipantId, HEARTBEAT_MS } from "../lib/identity";
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
  presence: [],                         // M2: participant list from presence WS events
  _ws: null,
  _visHandler: null,                   // M1: visibilitychange handler ref for cleanup
  _heartbeat: null,                    // M2: setInterval handle for presence heartbeat
  _unloadHandler: null,                // M2: pagehide handler ref for cleanup

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
      // U10: switching to a DIFFERENT session leaves no trace on the old one
      // otherwise — the server only learns via the 45s presence lease TTL
      // (ghost presence in the meantime). leavePresence() reads the still-open
      // old session from state, so it must run before it's torn down below.
      const prevSessionId = get().session?.session_id;
      if (prevSessionId && prevSessionId !== sessionId) {
        get().leavePresence();
      }
      await api.createSession(year, month);
      const session = await api.getSession(sessionId);
      // Tear down any prior WS, vis handler, heartbeat, and unload handler,
      // then reconnect for the new session.
      get()._ws?.close();
      const prevVisHandler = get()._visHandler;
      if (prevVisHandler) document.removeEventListener("visibilitychange", prevVisHandler);
      const prevHeartbeat = get()._heartbeat;
      if (prevHeartbeat) clearInterval(prevHeartbeat);
      const prevUnloadHandler = get()._unloadHandler;
      if (prevUnloadHandler) window.removeEventListener("pagehide", prevUnloadHandler);
      const ws = createWSClient(sessionId, {
        onEvent: get()._handleWSEvent,
        onReconnect: () => get().refetchSession(sessionId),
      });
      // Auto-heal: re-fetch on tab refocus (a dropped event leaves us stale).
      // Guard for SSR/node-env (document absent outside a browser).
      let visHandler = null;
      if (typeof document !== "undefined") {
        visHandler = () => {
          if (document.visibilityState === "visible") get().refetchSession(sessionId);
        };
        document.addEventListener("visibilitychange", visHandler);
      }
      // Nota: _visHandler solo se limpia al volver a llamar openMonth (no hay acción
      // de "cerrar sesión" explícita todavía — limitación conocida de M1).
      set({ session, loading: false, _ws: ws, _visHandler: visHandler, _heartbeat: null, _unloadHandler: null, scanningCells: new Set(), scanProgress: null, historyDrawer: null, presence: [] });
      // M2: start the presence heartbeat for the newly opened session.
      get().startPresence();
      // M2: register pagehide beacon so the server knows we left on hard-close/reload.
      if (typeof window !== "undefined") {
        const sid = session.session_id;
        const unloadHandler = () => api.beaconLeave(sid, { participant_id: getParticipantId() });
        window.addEventListener("pagehide", unloadHandler);
        set({ _unloadHandler: unloadHandler });
      }
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
      await api.scanFileOcr(sessionId, hospital, sigla, filename, getParticipantId());
    } catch (error) {
      // B1: another participant holds the cell → the OCR never starts. Toast the
      // holder and no-op (no optimistic state to revert; nothing to refetch).
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        toast.error(`${who} está editando esta celda`);
        return;
      }
      set({ error: String(error) });
    }
  },

  // E5 — clear near-match suspects for a cell. `entry` = { pdf_name, page_index }
  // drops one; omit it to clear all. Optimistic, then persists.
  clearNearMatches: async (sessionId, hospital, sigla, entry) => {
    const participantId = getParticipantId();
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
      await api.clearNearMatches(sessionId, hospital, sigla, entry, participantId);
    } catch (error) {
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
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
    const participantId = getParticipantId();
    try {
      const updatedCell = await api.applyRatio(sessionId, hospital, sigla, n, participantId);
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
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
      set({ error: String(error) });
      throw error; // re-throw so the caller can show a failure toast (don't claim success)
    }
  },

  // F1 (Task 2.4) — reconcile orphan worker/check marks (migrate/discard). The
  // route returns the enriched cell (canonical worker_count) → merge it in.
  // Returns the enriched cell on success and NULL on a handled 409 (the lock
  // toast already fired here) so the panel only claims success on a truthy
  // result; any other error re-throws for the panel's failure toast.
  reconcileWorkerMarks: async (sessionId, hospital, sigla, payload) => {
    const participantId = getParticipantId();
    try {
      const cell = await api.reconcileWorkerMarks(
        sessionId, hospital, sigla, payload, participantId,
      );
      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = { ...hosp[sigla], ...cell };
        cells[hospital] = hosp;
        return { session: { ...prev.session, cells } };
      });
      return cell;
    } catch (error) {
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return null; // handled: the panel must NOT toast success on top
      }
      set({ error: String(error) });
      throw error; // re-throw so the panel shows a failure toast (don't claim success)
    }
  },

  saveOverride: async (sessionId, hospital, sigla, value, opts = {}) => {
    const key = `${hospital}|${sigla}`;
    const controller = new AbortController();
    const participantId = getParticipantId();

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
        { signal: controller.signal, manual: opts.manual, participantId },
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
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        set((prev) => {
          const cleanedPending = new Map(prev._pendingSave);
          if (cleanedPending.get(key)?.controller === controller) {
            cleanedPending.delete(key);
          }
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { _pendingSave: cleanedPending, pendingSaves: np };
        });
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
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
    const participantId = getParticipantId();

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
        { signal: controller.signal, participantId },
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
          // Backend recomputes all_reliable after the override (resolving the
          // last unreliable file flips the green dot); merge it because the F15
          // guard drops this write's own cell_updated echo (saveNote pattern).
          all_reliable: result.all_reliable,
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
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        const tickKey = `${hospital}|${sigla}`;
        set((prev) => {
          const cleanedPending = new Map(prev._pendingSave);
          if (cleanedPending.get(key)?.controller === controller) {
            cleanedPending.delete(key);
          }
          const np = { ...prev.pendingSaves };
          delete np[key];
          // Bump filesTick so FileList re-fetches: the per-file InlineEditCount
          // holds the typed value locally, so after a blocked edit we force a
          // re-sync to server truth (the success path bumps it for the same reason).
          return {
            _pendingSave: cleanedPending,
            pendingSaves: np,
            filesTick: { ...prev.filesTick, [tickKey]: (prev.filesTick[tickKey] ?? 0) + 1 },
          };
        });
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
      // U2: a generic (non-409) failure reverts visibly instead of leaving a
      // sticky global error banner — toast it + bump filesTick so FileList/the
      // lightbox re-fetch and drop the optimistic value that never saved.
      const tickKey = `${hospital}|${sigla}`;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          filesTick: { ...prev.filesTick, [tickKey]: (prev.filesTick[tickKey] ?? 0) + 1 },
        };
      });
      toast.error(`No se pudo guardar el conteo del archivo: ${String(error)}`);
    }
  },

  confirmCell: async (sessionId, hospital, sigla, confirmed) => {
    const key = `${hospital}|${sigla}|confirm`;
    const controller = new AbortController();
    const participantId = getParticipantId();

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
        sessionId, hospital, sigla, confirmed, { signal: controller.signal, participantId },
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
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        set((prev) => {
          const cleanedPending = new Map(prev._pendingSave);
          if (cleanedPending.get(key)?.controller === controller) {
            cleanedPending.delete(key);
          }
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { _pendingSave: cleanedPending, pendingSaves: np };
        });
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
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
    const participantId = getParticipantId();

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
        sessionId, hospital, sigla, patch, { signal: controller.signal, participantId },
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
          // Backend recomputes all_reliable after the worker PATCH (checks cells
          // light green on 'terminado'); merge it because the F15 guard drops
          // this write's own cell_updated echo (saveNote pattern).
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
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        set((prev) => {
          const cleanedPending = new Map(prev._pendingSave);
          if (cleanedPending.get(key)?.controller === controller) {
            cleanedPending.delete(key);
          }
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { _pendingSave: cleanedPending, pendingSaves: np };
        });
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
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
    const participantId = getParticipantId();

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
        sessionId, hospital, sigla, patch, { signal: controller.signal, participantId },
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
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        set((prev) => {
          const cleanedPending = new Map(prev._pendingSave);
          if (cleanedPending.get(key)?.controller === controller) {
            cleanedPending.delete(key);
          }
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { _pendingSave: cleanedPending, pendingSaves: np };
        });
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
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
      await api.createReorgOp(
        sessionId,
        {
          source: { hospital, sigla, ...opDraft.source },
          dest: opDraft.dest,
          op_type: opDraft.op_type,
          empresa: opDraft.empresa,
          preserve_date: opDraft.preserve_date,
          rotation_deg: opDraft.rotation_deg,
          doc_count: opDraft.doc_count,
          worker_count: opDraft.worker_count,
          note: opDraft.note,
        },
        getParticipantId(),
      );
      const session = await api.getSession(sessionId);
      set({ session });
    } catch (error) {
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
      toast.error(`No se pudo crear la operación: ${String(error)}`);
      throw error;
    }
  },

  deleteReorgOp: async (sessionId, opId) => {
    try {
      await api.deleteReorgOp(sessionId, opId, getParticipantId());
      const session = await api.getSession(sessionId);
      set({ session });
    } catch (error) {
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "Otro usuario";
        toast.error(`${who} está editando esta celda`);
        get().refetchSession(sessionId);
        return;
      }
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
      case "cell_skipped": {
        // The scanner skipped this cell because a human is editing it (M3b).
        // Do NOT touch session.cells (the cell wasn't processed) and accumulate
        // the cell into scanProgress.skipped for the summary UI. The backend does
        // NOT emit cell_scanning for a skipped cell, so it's normally not in
        // scanningCells — the delete is defensive cleanup only. Derive everything
        // from `s` so the update stays consistent if events batch.
        set((s) => {
          const next = new Set(s.scanningCells);
          next.delete(cellKey(event.hospital, event.sigla));
          return {
            scanningCells: next,
            scanProgress: s.scanProgress
              ? {
                  ...s.scanProgress,
                  skipped: [
                    ...(s.scanProgress.skipped ?? []),
                    { hospital: event.hospital, sigla: event.sigla },
                  ],
                }
              : s.scanProgress,
          };
        });
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
        const key = cellKey(event.hospital, event.sigla);
        // F15: an in-flight local save (saveOverride/savePerFileOverride/etc.)
        // owns this cell right now — a wholesale replace here would clobber
        // the operator's optimistic edit mid-flight. Keys are `hospital|sigla`
        // (cell-level saves) or `hospital|sigla|<field>` (per-file/note/etc.),
        // so match the exact key or that prefix — NOT a bare startsWith(key),
        // which would also match an unrelated sigla like `HPV|odiXYZ`. Once
        // the save resolves (its own handler applies the server value and
        // clears _pendingSave), a later cell_updated reconciles normally.
        const hasPending = [...state._pendingSave.keys()].some(
          (k) => k === key || k.startsWith(`${key}|`),
        );
        if (hasPending) break;
        const cells = { ...session.cells };
        const hosp = { ...(cells[event.hospital] || {}) };
        // Reemplazo de celda COMPLETA (§4). En el flujo de escaneo llega DESPUÉS de
        // cell_done; si llegaran fuera de orden igual es seguro (el merge parcial de
        // cell_done solo escribe un subconjunto de campos sobre datos ya frescos).
        hosp[event.sigla] = event.cell;
        cells[event.hospital] = hosp;
        const filesTick = {
          ...state.filesTick,
          [key]: (state.filesTick[key] ?? 0) + 1,
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
      case "scan_complete": {
        // Scan run terminated → no cell can still be scanning. Defensive:
        // clears any cell that never emitted its own cell_done/cell_error.
        // Finalize the PDF bar at 100% without clobbering its denominator.
        // M3b: merge any cells that were skipped by the scanner (locked by a
        // human) into scanProgress.skipped so the UI can offer a re-scan.
        const skippedFromEvent = event.skipped ?? [];
        set((s) => {
          const prevSkipped = s.scanProgress?.skipped ?? [];
          // Merge: cells accumulated via cell_skipped events + any in the
          // final summary (de-dup by hospital+sigla to be safe).
          const merged = [...prevSkipped];
          for (const sk of skippedFromEvent) {
            if (!merged.some((x) => x.hospital === sk.hospital && x.sigla === sk.sigla)) {
              merged.push(sk);
            }
          }
          return {
            scanningCells: new Set(),
            scanProgress: {
              ...s.scanProgress,
              terminal: "complete",
              done: s.scanProgress?.total ?? 0,
              skipped: merged,
            },
          };
        });
        // Auto-dismiss after 5s — BUT only when there are no skipped cells.
        // When skipped.length > 0 the banner persists until the user acts.
        setTimeout(() => set((s) => {
          if (s.scanProgress?.terminal !== "complete") return {};
          if ((s.scanProgress?.skipped?.length ?? 0) > 0) return {};
          return { scanProgress: null };
        }), 5000);
        break;
      }
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
        // U6: a Cancelar click ends here too (error: "cancelled") — that's an
        // intentional stop, not a failure, so a neutral toast replaces the
        // sticky global error banner the generic branch below sets.
        if (event.error === "cancelled") {
          toast("Escaneo cancelado");
          set((s) => ({
            fileScan: s.fileScan ? { ...s.fileScan, terminal: "cancelled" } : null,
          }));
          setTimeout(
            () => set((s) => (s.fileScan?.terminal === "cancelled" ? { fileScan: null } : s)),
            2000,
          );
          break;
        }
        // F12: the merge-time lock re-check rejected a stale merge (another
        // participant claimed the cell while the OCR was in flight). Same
        // "<name> está editando esta celda" toast + re-sync as the other lock
        // conflicts (e.g. savePerFileOverride's 409) — nothing broke, so this
        // skips the sticky global error banner too.
        if (event.error === "cell_locked") {
          const who = event.lock_holder?.name ?? "Otro usuario";
          const tickKey = `${event.hospital}|${event.sigla}`;
          toast.error(`${who} está editando esta celda`);
          set((s) => ({
            fileScan: s.fileScan ? { ...s.fileScan, terminal: "cancelled" } : null,
            filesTick: { ...s.filesTick, [tickKey]: (s.filesTick[tickKey] ?? 0) + 1 },
          }));
          setTimeout(
            () => set((s) => (s.fileScan?.terminal === "cancelled" ? { fileScan: null } : s)),
            2000,
          );
          if (state.session?.session_id) get().refetchSession(state.session.session_id);
          break;
        }
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
      case "presence":
        // M2: replace the participant list wholesale (server is authoritative).
        set({ presence: event.participants ?? [] });
        break;
      default:
        // Unknown event types ignored
    }
  },

  // M2 — Presence lifecycle actions -------------------------------------------

  /**
   * Start (or restart) the presence heartbeat for the currently open session.
   * Idempotent: calling it while one is already running replaces the interval
   * rather than stacking a second one. No-ops if no session is open or no
   * identity has been set (user hasn't named themselves yet).
   */
  startPresence: () => {
    const { session, _heartbeat } = get();
    // Guard: localStorage is not available in node/test environments.
    if (typeof localStorage === "undefined") return;
    const id = getIdentity();
    if (!session || !id) return;              // no month open or not named yet
    if (_heartbeat) clearInterval(_heartbeat); // never double-start
    const sid = session.session_id;
    const beat = () =>
      api.presenceHeartbeat(sid, { participant_id: id.participant_id, name: id.name, color: id.color })
        .then((r) => set({ presence: r.participants ?? [] }))
        .catch(() => {});
    beat();                                    // immediate join
    set({ _heartbeat: setInterval(beat, HEARTBEAT_MS) });
  },

  /**
   * Tell the server which cell this participant is currently focused on.
   * Fire-and-forget; no-op if no identity or no session.
   * @param {string} cell  — e.g. "HRB|odi"
   */
  setFocus: (cell) => {
    const { session } = get();
    if (typeof localStorage === "undefined") return;
    const id = getIdentity();
    if (id && session) {
      // Fire-and-forget: a dead/unreachable backend must not surface as an
      // unhandled promise rejection (Fase-3 follow-up).
      api
        .presenceFocus(session.session_id, { participant_id: id.participant_id, cell })
        .catch(() => {});
    }
  },

  /**
   * Stop the heartbeat and notify the server that this participant left.
   * Called on intentional sign-out or identity reset; the pagehide beacon
   * covers hard-close scenarios.
   */
  leavePresence: () => {
    const { session, _heartbeat } = get();
    if (_heartbeat) clearInterval(_heartbeat);
    if (typeof localStorage !== "undefined") {
      const id = getIdentity();
      // Fire-and-forget: a dead/unreachable backend must not surface as an
      // unhandled promise rejection (Fase-3 follow-up).
      if (id && session) {
        api.presenceLeave(session.session_id, { participant_id: id.participant_id }).catch(() => {});
      }
    }
    set({ _heartbeat: null, presence: [] });
  },
}));
