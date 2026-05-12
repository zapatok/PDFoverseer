const COLORS = {
  high: "bg-emerald-700/30 text-emerald-300 border-emerald-700",
  medium: "bg-amber-700/30 text-amber-300 border-amber-700",
  low: "bg-red-700/30 text-red-300 border-red-700",
  manual: "bg-purple-700/30 text-purple-300 border-purple-700",
};

export default function ConfidenceBadge({ confidence }) {
  if (!confidence) return null;
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${COLORS[confidence] || COLORS.low}`}>
      {confidence.toUpperCase()}
    </span>
  );
}
