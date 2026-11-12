import { freeMargin, num, THRESHOLD_NAMES } from '../lib/format.js';

const MARKS = [
  ['yellow', 'amarillo', '#facc15'],
  ['orange', 'naranja', '#fb923c'],
  ['red', 'rojo', '#ef4444'],
];

/** Barra visual de un valor frente a los umbrales OFICIALES. Sin umbrales: "umbral no publicado". */
export default function LevelBar({ value, thresholds, unit }) {
  if (value == null) return null;
  const published = thresholds ? MARKS.filter(([key]) => thresholds[key] != null) : [];
  if (!published.length) {
    return (
      <div className="mt-2">
        <div className="h-3 w-full rounded-full bg-slate-700" aria-hidden="true">
          <div className="h-3 w-1/3 rounded-full bg-sky-400" />
        </div>
        <p className="mt-1.5 text-sm text-slate-300">
          Sin referencia oficial para saber si es mucho o poco: <span className="font-bold text-sky-300">umbral no publicado</span>
        </p>
      </div>
    );
  }
  const top = Math.max(value, ...published.map(([key]) => thresholds[key])) * 1.12;
  const pct = (v) => `${Math.max(0, Math.min(100, (v / top) * 100))}%`;
  const margin = freeMargin(value, thresholds);
  const reached = [...published].reverse().find(([key]) => value >= thresholds[key]);
  return (
    <div className="mt-2">
      <div className="relative h-5 w-full rounded-full bg-slate-700" role="img" aria-label={`Valor actual ${num(value)} ${unit} frente a los umbrales oficiales`}>
        <div className="h-5 rounded-full" style={{ width: pct(value), background: reached ? reached[2] : '#22c55e' }} />
        {published.map(([key, name, color]) => (
          <span
            key={key}
            aria-label={`Umbral ${name}: ${num(thresholds[key])} ${unit}`}
            title={`Umbral ${name}: ${num(thresholds[key])} ${unit}`}
            className="absolute top-[-3px] h-[26px] w-1 rounded"
            style={{ left: pct(thresholds[key]), background: color }}
          />
        ))}
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-300">
        {published.map(([key, name, color]) => (
          <li key={key} className="flex items-center gap-1">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
            {name} {num(thresholds[key])} {unit}
          </li>
        ))}
      </ul>
      {margin.next ? (
        <p className="mt-1 text-sm text-slate-200">
          Margen libre: <strong>{num(margin.margin)} {unit}</strong> hasta el {THRESHOLD_NAMES[margin.next]}
        </p>
      ) : (
        <p className="mt-1 text-sm font-bold text-red-300">
          {published.length === 3
            ? 'Por encima de todos los umbrales oficiales.'
            : 'Por encima de los umbrales oficiales publicados (la fuente no publica niveles superiores).'}
        </p>
      )}
    </div>
  );
}
