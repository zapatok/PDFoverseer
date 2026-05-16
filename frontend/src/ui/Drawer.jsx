import { useEffect, useRef } from "react";
import { X } from "lucide-react";

/**
 * Panel lateral derecho, no-modal. El contenido detrás permanece interactivo
 * (sin overlay, sin focus-trap) — a propósito: el SparkGrid debe seguir
 * clickeable mientras el drawer está abierto.
 *
 *   <Drawer open={...} onClose={...} title={<...>}>
 *     ...contenido...
 *   </Drawer>
 *
 * Siempre montado (para la transición). Cuando !open: deslizado fuera de
 * pantalla + pointer-events-none para no capturar clicks. Al cerrar, si el
 * foco quedó dentro del panel (p. ej. el usuario cerró con la X), se devuelve
 * al elemento que lo abrió — un contenedor aria-hidden no puede contener el
 * foco.
 */
export default function Drawer({ open, onClose, title, children }) {
  const asideRef = useRef(null);
  const openerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Al abrir, recordar quién tenía el foco; al cerrar, si el foco quedó
  // atrapado dentro del panel ya oculto (aria-hidden), devolvérselo.
  useEffect(() => {
    if (open) {
      openerRef.current = document.activeElement;
      return undefined;
    }
    const aside = asideRef.current;
    if (aside && aside.contains(document.activeElement)) {
      const opener = openerRef.current;
      if (opener instanceof HTMLElement && opener.isConnected) {
        opener.focus();
      } else {
        document.activeElement.blur();
      }
    }
    return undefined;
  }, [open]);

  return (
    <aside
      ref={asideRef}
      aria-hidden={!open}
      className={[
        "fixed top-0 right-0 bottom-0 z-40 w-[420px]",
        "bg-po-panel border-l border-po-border shadow-2xl",
        "flex flex-col transition-transform duration-200 ease-out",
        open ? "translate-x-0" : "translate-x-full pointer-events-none",
      ].join(" ")}
    >
      <header className="px-4 py-3 border-b border-po-border flex items-center gap-3 shrink-0">
        <div className="flex-1 min-w-0">{title}</div>
        <button
          type="button"
          onClick={onClose}
          className="text-po-text-muted hover:text-po-text shrink-0"
          aria-label="Cerrar"
        >
          <X size={18} strokeWidth={1.75} />
        </button>
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
    </aside>
  );
}
