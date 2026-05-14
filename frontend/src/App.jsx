import * as Tooltip from "@radix-ui/react-tooltip";
import { Toaster } from "sonner";
import { useSessionStore } from "./store/session";
import MonthOverview from "./views/MonthOverview";
import HospitalDetail from "./views/HospitalDetail";
import PDFLightbox from "./components/PDFLightbox";
import ScanProgress from "./components/ScanProgress";

export default function App() {
  const { view, hospital, setView } = useSessionStore();

  return (
    <Tooltip.Provider delayDuration={300}>
      <div className="min-h-screen bg-po-bg text-po-text font-sans">
        <header className="px-6 py-4 border-b border-po-border">
          <h1 className="text-lg font-semibold">PDFoverseer</h1>
        </header>
        <main className="px-6 py-6 max-w-[1600px] mx-auto">
          {view === "month" && <MonthOverview />}
          {view === "hospital" && (
            <HospitalDetail hospital={hospital} onBack={() => setView("month")} />
          )}
        </main>
        <PDFLightbox />
        <ScanProgress />
        <Toaster position="bottom-right" theme="dark" className="z-[60]" />
      </div>
    </Tooltip.Provider>
  );
}
