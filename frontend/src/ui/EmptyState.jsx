export default function EmptyState({ icon: Icon, title, description, action, className = "" }) {
  return (
    <div className={["flex flex-col items-center text-center py-8 px-4 gap-3", className].join(" ")}>
      {Icon && <Icon size={32} strokeWidth={1.5} className="text-po-text-subtle" />}
      {title && <h3 className="text-sm font-medium text-po-text">{title}</h3>}
      {description && <p className="text-xs text-po-text-muted max-w-xs">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
