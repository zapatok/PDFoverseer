import * as RadixPopover from "@radix-ui/react-popover";

/**
 * <Popover open={...} onOpenChange={...}>
 *   <Popover.Trigger asChild>{trigger}</Popover.Trigger>
 *   <Popover.Content>{content}</Popover.Content>
 * </Popover>
 *
 * Minimal trigger+content API over Radix Popover, mirroring ui/Dialog's
 * compound-component convention. Content is portalized to body — it never
 * clips inside a scrollable/virtualized ancestor (§A3), and Radix moves
 * focus into it on open + restores it on Escape/outside-click close.
 */
export default function Popover({ open, onOpenChange, children }) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      {children}
    </RadixPopover.Root>
  );
}

Popover.Trigger = function PopoverTrigger({ children, asChild = true }) {
  return <RadixPopover.Trigger asChild={asChild}>{children}</RadixPopover.Trigger>;
};

Popover.Content = function PopoverContent({
  children,
  className = "",
  side = "bottom",
  align = "end",
  sideOffset = 4,
}) {
  return (
    <RadixPopover.Portal>
      <RadixPopover.Content
        side={side}
        align={align}
        sideOffset={sideOffset}
        className={[
          "z-[70] rounded-lg border border-po-border bg-po-panel shadow-lg outline-none",
          className,
        ].join(" ")}
      >
        {children}
      </RadixPopover.Content>
    </RadixPopover.Portal>
  );
};
