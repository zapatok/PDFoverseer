import { create } from "zustand";
import { api } from "../lib/api";

export const useSessionStore = create((set, get) => ({
  view: "month",         // "month" | "hospital"
  hospital: null,        // currently-selected hospital
  months: [],
  session: null,
  loading: false,
  error: null,

  setView: (view) => set({ view }),

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
      set({ session, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  selectHospital: (hospital) => set({ view: "hospital", hospital }),

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

  generateOutput: async (sessionId) => {
    set({ loading: true, error: null });
    try {
      const result = await api.generateOutput(sessionId);
      set({ loading: false });
      return result;
    } catch (error) {
      set({ error: String(error), loading: false });
      throw error;
    }
  },
}));
