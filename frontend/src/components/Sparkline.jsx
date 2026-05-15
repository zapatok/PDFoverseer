const TONE_STROKE = {
  neutral: "stroke-po-accent",
  warn:    "stroke-po-suspect",
  muted:   "stroke-po-text-subtle",
};

const TONE_FILL = {
  neutral: "fill-po-accent",
  warn:    "fill-po-suspect",
  muted:   "fill-po-text-subtle",
};

const W = 80;
const H = 28;
const PAD_Y = 4;

export default function Sparkline({ data, tone = "neutral" }) {
  if (!data || data.length === 0) {
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-label="Sin datos">
        <line
          x1={0} y1={H / 2} x2={W} y2={H / 2}
          className="stroke-po-text-subtle"
          strokeWidth={1}
          strokeDasharray="2,2"
        />
      </svg>
    );
  }

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = Math.max(max - min, 1);
  const stepX = data.length > 1 ? W / (data.length - 1) : 0;
  const yFor = (v) => PAD_Y + (1 - (v - min) / range) * (H - 2 * PAD_Y);
  const xFor = (i) => i * stepX;

  if (data.length === 1) {
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <circle cx={W / 2} cy={H / 2} r={2.5} className={TONE_FILL[tone]} />
      </svg>
    );
  }

  const points = data.map((v, i) => `${xFor(i)},${yFor(v)}`).join(" ");
  const lastIdx = data.length - 1;

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <polyline
        fill="none"
        strokeWidth={1.5}
        className={TONE_STROKE[tone]}
        points={points}
      />
      <circle
        cx={xFor(lastIdx)}
        cy={yFor(data[lastIdx])}
        r={2}
        className={TONE_FILL[tone]}
      />
    </svg>
  );
}
