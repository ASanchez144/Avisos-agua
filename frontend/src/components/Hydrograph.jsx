import { num } from '../lib/format.js';

const W = 320;
const H = 170;
const RAIN_H = 52;
const PAD = 6;

/** Hidrograma combinado: barras de lluvia arriba (hacia abajo) y curva de caudal abajo. */
export default function Hydrograph({ history }) {
  const points = [...(history || [])]
    .filter((r) => r.timestamp_utc && (r.flow_m3s != null || r.rain_1h_mm != null))
    .sort((a, b) => a.timestamp_utc.localeCompare(b.timestamp_utc));
  if (points.length < 2) {
    return <p className="text-sm text-slate-400">Aún no hay histórico suficiente para dibujar la gráfica.</p>;
  }
  const t0 = new Date(points[0].timestamp_utc).getTime();
  const t1 = new Date(points[points.length - 1].timestamp_utc).getTime();
  const x = (r) => PAD + ((new Date(r.timestamp_utc).getTime() - t0) / Math.max(1, t1 - t0)) * (W - 2 * PAD);
  const flows = points.filter((r) => r.flow_m3s != null);
  const rains = points.filter((r) => r.rain_1h_mm != null);
  const maxFlow = Math.max(...flows.map((r) => r.flow_m3s), 0.001);
  const maxRain = Math.max(...rains.map((r) => r.rain_1h_mm), 0.001);
  const y = (v) => H - PAD - (v / maxFlow) * (H - RAIN_H - 3 * PAD);
  const line = flows.map((r, i) => `${i ? 'L' : 'M'}${x(r).toFixed(1)},${y(r.flow_m3s).toFixed(1)}`).join(' ');
  const hours = Math.round(((t1 - t0) / 3600000) * 10) / 10;
  const barWidth = Math.max(1.5, (W - 2 * PAD) / Math.max(rains.length, 1) - 1);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
        aria-label={`Gráfica de las últimas ${num(hours, 1)} horas: lluvia arriba y caudal abajo. Caudal máximo ${num(maxFlow)} metros cúbicos por segundo.`}>
        <line x1={PAD} x2={W - PAD} y1={RAIN_H + PAD} y2={RAIN_H + PAD} stroke="#334155" strokeDasharray="3 3" />
        {rains.map((r) => (
          <rect key={r.timestamp_utc} x={x(r) - barWidth / 2} y={PAD} width={barWidth}
            height={Math.max(0, (r.rain_1h_mm / maxRain) * (RAIN_H - PAD))} fill="#38bdf8" opacity="0.85" />
        ))}
        {flows.length > 1 && <path d={line} fill="none" stroke="#a78bfa" strokeWidth="2.5" strokeLinejoin="round" />}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-300">
        <span className="flex items-center gap-1"><span aria-hidden="true" className="inline-block h-2.5 w-2.5 bg-sky-400" /> Lluvia (barras, máx. {num(maxRain, 1)} l/m² en 1 h)</span>
        {flows.length > 1 && <span className="flex items-center gap-1"><span aria-hidden="true" className="inline-block h-1 w-4 bg-violet-400" /> Caudal (curva, máx. {num(maxFlow)})</span>}
        <span>Últimas {num(hours, 1)} h</span>
      </figcaption>
    </figure>
  );
}
