import * as RadixDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

/**
 * Compound component:
 *   <Dialog open={...} onOpenChange={...}>
 *     <Dialog.Header>...</Dialog.Header>
 *     <Dialog.Body>...</Dialog.Body>
 *   </Dialog>
 *
 * Renders overlay (z-50) + content (z-51) in a portal. ESC + click-outside
 * close. Focus trap inside the content. Returns null when !open.
 */
export default function Dialog({ open, onOpenChange, children }) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 bg-black/70" />
        <RadixDialog.Content className="fixed inset-4 z-[51] bg-po-bg border border-po-border rounded-xl shadow-2xl flex flex-col focus-visible:outline-none">
          {children}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

Dialog.Header = function DialogHeader({ children }) {
  return (
    <header className="px-5 py-3 border-b border-po-border flex items-center gap-3">
      <div className="flex-1 min-w-0">{children}</div>
      <RadixDialog.Close className="text-po-text-muted hover:text-po-text shrink-0">
        <X size={18} strokeWidth={1.75} />
      </RadixDialog.Close>
    </header>
  );
};

Dialog.Body = function DialogBody({ children, className = "" }) {
  return <div className={["flex-1 min-h-0 flex", className].join(" ")}>{children}</div>;
};

// Accessibility: Radix requires Dialog.Title and Dialog.Description for screen
// readers. Re-export so consumers can include them. If a consumer doesn't, Radix
// will console.warn in dev — that warning is benign for a single-user desktop
// app but we provide the slots for hygiene.
Dialog.Title = RadixDialog.Title;
Dialog.Description = RadixDialog.Description;
