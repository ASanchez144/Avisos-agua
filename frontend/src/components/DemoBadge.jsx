import { FlaskConical } from 'lucide-react';

/** Etiqueta grande e inconfundible del modo demostración. Va en cada pantalla. */
export default function DemoBadge({ compact = false }) {
  return (
    <div
      data-testid="demo-badge"
      className={`flex items-center justify-center gap-2 bg-fuchsia-600 font-black uppercase tracking-wide text-white ${
        compact ? 'rounded-md px-2 py-1 text-xs' : 'px-3 py-2 text-base sm:text-lg'
      }`}
    >
      <FlaskConical aria-hidden="true" className={compact ? 'h-4 w-4' : 'h-6 w-6'} />
      <span>DATOS DE DEMOSTRACIÓN</span>
    </div>
  );
}
