export default function HospitalCard({ hospital, total, status, onClick }) {
  const isMissing = status === "missing";
  return (
    <button
      onClick={onClick}
      disabled={isMissing}
      className={`block w-full text-left rounded-lg border p-4 transition
        ${isMissing
          ? "border-slate-800 bg-slate-900/50 opacity-50 cursor-not-allowed"
          : "border-slate-700 bg-slate-900 hover:bg-slate-800 cursor-pointer"
        }`}
    >
      <div className="flex justify-between items-baseline">
        <h3 className="text-lg font-semibold">{hospital}</h3>
        <span className="text-sm text-slate-400">
          {isMissing ? "no normalizado" : ""}
        </span>
      </div>
      <p className="text-3xl font-bold mt-3">{isMissing ? "—" : total}</p>
      <p className="text-xs text-slate-400 mt-1">total documentos</p>
    </button>
  );
}
