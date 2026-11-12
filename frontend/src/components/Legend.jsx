import { Camera } from 'lucide-react';
import { STATUS } from '../lib/status.js';

/** Leyenda: cada estado con su icono, su letra y su nombre. */
export default function Legend() {
  return (
    <details className="rounded-xl border border-slate-600 bg-slate-900/95 text-sm text-slate-100 shadow-lg">
      <summary className="cursor-pointer px-3 py-2 font-bold">Leyenda</summary>
      <ul className="space-y-1.5 px-3 pb-3">
        {Object.entries(STATUS).map(([key, meta]) => (
          <li key={key} className="flex items-center gap-2">
            <span className="flex h-6 w-9 items-center justify-center gap-0.5 rounded-full text-[11px] font-extrabold"
              style={{ background: meta.color, color: meta.text }}>
              <meta.Icon aria-hidden="true" className="h-3.5 w-3.5" />
              {meta.short}
            </span>
            {meta.label}
          </li>
        ))}
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="flex h-6 w-9 items-center justify-center"><Camera className="h-4 w-4" /></span>
          Estación con cámara oficial que enfoca el río
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="flex h-7 w-9 items-center justify-center rounded-full border-2 border-slate-900 bg-slate-300 text-xs font-extrabold text-slate-900">12</span>
          Grupo de estaciones: lleva el color del PEOR estado
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="w-9 border-t-4 border-dashed border-orange-500" />
          Crecida en camino (estimación)
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="w-9 border-t-2 border-dashed border-slate-400" />
          Tramo vigilado
        </li>
      </ul>
    </details>
  );
}
