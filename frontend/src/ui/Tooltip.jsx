import * as RadixTooltip from "@radix-ui/react-tooltip";

/**
 * <Tooltip content="...">{trigger}</Tooltip>
 *
 * Provider lives in App.jsx with delayDuration=300. This wrapper assumes
 * the provider is in scope.
 */
export default function Tooltip({ content, side = "top", children }) {
  if (!content) return children;
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side={side}
          sideOffset={6}
          className="z-[70] rounded-md bg-po-panel border border-po-border px-2.5 py-1.5 text-xs text-po-text shadow-lg max-w-xs"
        >
          {content}
          <RadixTooltip.Arrow className="fill-po-border" />
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
