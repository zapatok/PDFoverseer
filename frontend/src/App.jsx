import { useEffect, useState } from "react";
import { useSessionStore } from "./store/session";
import MonthOverview from "./views/MonthOverview";
import HospitalDetail from "./views/HospitalDetail";

export default function App() {
  const { view, hospital, setView } = useSessionStore();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="px-6 py-4 border-b border-slate-800 flex justify-between items-center">
        <h1 className="text-lg font-semibold">PDFoverseer</h1>
        <span className="text-sm text-slate-400">FASE 1 MVP</span>
      </header>
      <main className="p-6">
        {view === "month" && <MonthOverview />}
        {view === "hospital" && (
          <HospitalDetail hospital={hospital} onBack={() => setView("month")} />
        )}
      </main>
    </div>
  );
}
