export default function Skeleton({ className = "" }) {
  return (
    <span
      aria-hidden="true"
      className={["block bg-po-panel-hover rounded animate-pulse", className].join(" ")}
    />
  );
}
