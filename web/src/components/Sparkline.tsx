/* Спарклайн одной серии (динамика за 14 дней): тонкая линия цветом акцента,
   точка на последнем значении, без осей и легенды — подпись и итоговые числа
   живут текстом рядом (данные читаются и без наведения). */

export function Sparkline({
  values,
  width = 160,
  height = 36,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  if (values.length === 0) return null;
  const max = Math.max(...values, 1);
  const pad = 3;
  const stepX = (width - pad * 2) / Math.max(values.length - 1, 1);
  const y = (v: number) => height - pad - (v / max) * (height - pad * 2);
  const points = values.map((v, i) => `${(pad + i * stepX).toFixed(1)},${y(v).toFixed(1)}`);
  const lastX = pad + (values.length - 1) * stepX;
  const lastY = y(values[values.length - 1]);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label={`Динамика по дням: ${values.join(", ")}`}
      className="shrink-0"
    >
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r="3" fill="var(--accent)" />
    </svg>
  );
}
