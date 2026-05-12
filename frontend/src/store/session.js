import { create } from "zustand";

export const useSessionStore = create((set) => ({
  view: "month",
  hospital: null,
  setView: (view) => set({ view }),
}));
