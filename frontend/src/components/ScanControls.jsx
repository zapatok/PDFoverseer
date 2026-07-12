import { Scan } from "lucide-react";
import { useSessionStore } from "../store/session";
import Button from "../ui/Button";

export default function ScanControls({ hospital, selectedSiglas }) {
  // A6: per-field selector — only session_id is used here.
  const sessionId = useSessionStore((s) => s.session?.session_id);
  const scanOcr = useSessionStore((s) => s.scanOcr);

  const n = selectedSiglas.length;

  const onClick = () => {
    if (n === 0) return;
    const pairs = selectedSiglas.map((s) => [hospital, s]);
    scanOcr(sessionId, pairs);
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
