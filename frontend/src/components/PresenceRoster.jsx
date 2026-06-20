import { useSessionStore } from "../store/session";
import { rosterParticipants } from "../lib/presence";
import PresenceBadge from "./PresenceBadge";

/**
 * Overlapping avatar row of all participants currently in the session.
 * Renders nothing when the roster is empty.
 */
export default function PresenceRoster() {
  const presence = useSessionStore((s) => s.presence);
  const participants = rosterParticipants(presence);

  if (participants.length === 0) return null;

  return (
    <div className="flex items-center -space-x-2" aria-label="Participantes en sesión">
      {participants.map((p) => (
        <PresenceBadge key={p.participant_id} participant={p} size="md" />
      ))}
    </div>
  );
}
