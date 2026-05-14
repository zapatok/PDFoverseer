import { forwardRef } from "react";

const VARIANTS = {
  primary:     "bg-po-accent text-white hover:bg-po-accent-hover",
  secondary:   "bg-po-panel border border-po-border hover:border-po-border-strong text-po-text",
  ghost:       "text-po-text-muted hover:text-po-text hover:bg-po-panel-hover",
  destructive: "border border-po-error text-po-error hover:bg-po-error-bg",
};

const SIZES = {
  sm: "text-xs px-2.5 py-1",
  md: "text-sm px-3 py-1.5",
};

const Button = forwardRef(function Button(
  {
    variant = "secondary",
    size = "md",
    icon: Icon,
    disabled = false,
    type = "button",
    className = "",
    children,
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled}
      className={[
        "inline-flex items-center gap-1.5 rounded-md font-medium transition",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-po-accent",
        VARIANTS[variant],
        SIZES[size],
        className,
      ].join(" ")}
      {...props}
    >
      {Icon && <Icon size={16} strokeWidth={1.75} />}
      {children}
    </button>
  );
});

export default Button;
