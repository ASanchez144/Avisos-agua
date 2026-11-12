import { Clock, History } from 'lucide-react';
import { freshness } from '../lib/format.js';

/** "hace 12 min". Si el dato tiene más de 60 min, aviso visible. */
export default function Freshness({ timestamp, now = new Date(), limitMinutes = 60 }) {
  const f = freshness(timestamp, now, limitMinutes);
  if (f.stale) {
    return (
      <p role="alert" className="flex items-start gap-2 rounded-lg border border-amber-500 bg-amber-950 p-2 text-sm font-semibold text-amber-100">
        <History aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          Dato antiguo: última lectura {f.text}. No refleja la situación actual.
        </span>
      </p>
    );
  }
  return (
    <p className="flex items-center gap-1.5 text-sm text-slate-300">
      <Clock aria-hidden="true" className="h-4 w-4" />
      <span className="sr-only">Última lectura: </span>
      <span>{f.text}</span>
    </p>
  );
}
