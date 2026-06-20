import { useState } from "react";
import Dialog from "../ui/Dialog";
import Button from "../ui/Button";
import { useSessionStore } from "../store/session";
import { getIdentity, setIdentity, getParticipantId, COLORS, pickColor } from "../lib/identity";

/**
 * Modal dialog that asks the user for their name and color before joining.
 * Self-gates: only opens when localStorage has no identity yet.
 * On submit, persists identity and starts the presence heartbeat.
 */
export default function IdentityDialog() {
  const [open, setOpen] = useState(() => getIdentity() === null);
  const [name, setName] = useState("");
  const [color, setColor] = useState(() => pickColor(getParticipantId() ?? ""));

  const canSubmit = name.trim().length > 0;

  const handleSubmit = () => {
    if (!canSubmit) return;
    setIdentity({ name: name.trim(), color });
    // Start presence heartbeat even if a month was already open before naming.
    useSessionStore.getState().startPresence();
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Dialog.Header>
        <Dialog.Title className="text-base font-semibold text-po-text">
          ¿Cómo te llamas?
        </Dialog.Title>
      </Dialog.Header>

      <Dialog.Body className="flex-col p-6 gap-6 overflow-y-auto">
        <Dialog.Description className="text-sm text-po-text-muted">
          Tú y quien trabaje el mismo mes se verán en vivo.
        </Dialog.Description>

        {/* Name field */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="identity-name" className="text-sm font-medium text-po-text">
            Tu nombre
          </label>
          <input
            id="identity-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
            placeholder="Ej. Carla"
            autoFocus
            className={[
              "rounded-md border px-3 py-2 text-sm bg-po-panel text-po-text",
              "border-po-border focus:outline-none focus:ring-2 focus:ring-po-accent",
              "placeholder:text-po-text-subtle",
            ].join(" ")}
          />
        </div>

        {/* Color picker */}
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium text-po-text">Elige un color</span>
          <div className="flex items-center gap-2 flex-wrap">
            {COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setColor(c)}
                aria-label={`Color ${c}`}
                aria-pressed={color === c}
                className={[
                  "w-7 h-7 rounded-full transition focus:outline-none",
                  "focus-visible:ring-2 focus-visible:ring-po-accent",
                  color === c
                    ? "ring-2 ring-offset-2 ring-po-text ring-offset-po-bg"
                    : "ring-1 ring-po-border",
                ].join(" ")}
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        </div>

        {/* Submit */}
        <div className="flex justify-end pt-2">
          <Button
            variant="primary"
            size="md"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            Entrar
          </Button>
        </div>
      </Dialog.Body>
    </Dialog>
  );
}
