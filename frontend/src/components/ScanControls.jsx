import { Scan } from "lucide-react";
import { useSessionStore } from "../store/session";
import Button from "../ui/Button";

export default function ScanControls({ hospital, selectedSiglas }) {
  const session = useSessionStore((s) => s.session);
  const scanOcr = useSessionStore((s) => s.scanOcr);

  const n = selectedSiglas.length;

  const onClick = () => {
    if (n === 0) return;
    const pairs = selectedSiglas.map((s) => [hospital, s]);
    scanOcr(session.session_id, pairs);
  };

  let label;
  if (n === 0) label = "Selecciona categorías para OCR";
  else if (n === 1) label = "Escanear 1 categoría";
  else label = `Escanear ${n} categorías`;

  return (
    <Button
      variant={n > 0 ? "primary" : "secondary"}
      icon={Scan}
      disabled={n === 0}
      onClick={onClick}
    >
      {label}
    </Button>
  );
}
