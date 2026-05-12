const ICONS = {
  pending: { icon: "○", color: "text-slate-500" },
  scanning: { icon: "●", color: "text-blue-400 animate-pulse" },
  done_high: { icon: "✓", color: "text-emerald-400" },
  done_review: { icon: "⚠", color: "text-amber-400" },
  error: { icon: "✕", color: "text-red-400" },
  manual: { icon: "✎", color: "text-purple-400" },
};

export default function ScanIndicator({ status }) {
  const { icon, color } = ICONS[status] || ICONS.pending;
  return <span className={`text-lg ${color}`} aria-label={status}>{icon}</span>;
}
