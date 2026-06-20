import { Bot } from "lucide-react";
import Tooltip from "../ui/Tooltip";
import { initials } from "../lib/presence";

const SIZES = {
  sm: "w-5 h-5 text-[10px]",
  md: "w-7 h-7 text-xs",
};

// Icon sizes (px) matching the avatar container sizes above.
const ICON_SIZES = { sm: 11, md: 15 };

/**
 * Round avatar for a single presence participant.
 * Participant color is applied via inline style (it's dynamic data from COLORS,
 * not a theme token — the one allowed exception to po-* token rule).
 *
 * When participant.kind === "agent" (e.g. Claude), renders a Bot icon instead
 * of initials. Color still comes from participant.color (backend AGENT_COLOR).
 *
 * @param {{ participant: object, size?: "sm"|"md" }} props
 */
export default function PresenceBadge({ participant, size = "md" }) {
  const isAgent = participant.kind === "agent";

  return (
    <Tooltip content={participant.name} side="top">
      <span
        className={[
          "inline-flex items-center justify-center rounded-full",
          "font-semibold text-white select-none shrink-0",
          "ring-2 ring-po-bg",
          SIZES[size],
        ].join(" ")}
        style={{ backgroundColor: participant.color }}
        aria-label={participant.name}
      >
        {isAgent
          ? <Bot size={ICON_SIZES[size] ?? ICON_SIZES.md} strokeWidth={1.75} />
          : initials(participant.name)
        }
      </span>
    </Tooltip>
  );
}
