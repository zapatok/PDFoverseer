import { useRef, useState } from "react";

// Estado → estilo del anillo. La metáfora punteado→sólido = borrador→confirmado
// (spec §5.1); no gasta un tercer color ni choca con el ámbar de "sospechoso".
const RING = {
  empty: "border-2 border-dashed border-po-text-subtle text-po-text-subtle",
  pending: "border-2 border-dashed border-po-accent text-po-text",
  fixed: "border-2 border-po-accent bg-po-accent text-white",
};

/**
 * Burbuja flotante de conteo — solo display. El número lo teclea el visor
 * (Task 16) y lo pasa por `value`; aquí no hay `<input>`, así que `Supr`/`E`
 * nunca compiten con un campo de texto enfocado.
 *
 * @param {object} props
 * @param {"empty"|"pending"|"fixed"} props.state
 * @param {string|number} props.value - número a mostrar; "" cuando está vacía.
 */
export function WorkerBubble({ state, value }) {
  const [pos, setPos] = useState({ x: 0, y: 0 }); // offset de arrastre, no persistido
  const drag = useRef(null);

  const onPointerDown = (e) => {
    drag.current = { x: e.clientX, y: e.clientY, bx: pos.x, by: pos.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    setPos({
      x: drag.current.bx + (e.clientX - drag.current.x),
      y: drag.current.by + (e.clientY - drag.current.y),
    });
  };
  const onPointerUp = () => { drag.current = null; };

  return (
    <div
      className={`absolute right-6 flex h-20 w-20 cursor-grab select-none items-center justify-center rounded-full ${RING[state]}`}
      style={{ top: "50%", transform: `translate(${pos.x}px, calc(-50% + ${pos.y}px))` }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      <span className="text-2xl font-semibold tabular-nums">
        {value === "" || value == null ? "·" : value}
      </span>
    </div>
  );
}
