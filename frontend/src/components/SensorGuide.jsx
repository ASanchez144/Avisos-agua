import { BookOpen } from 'lucide-react';

const ITEMS = [
  ['Nivel', 'La altura del agua en un punto fijo del río, en metros. Es lo que se compara con los umbrales oficiales de aviso.'],
  ['Caudal', 'Cuánta agua pasa cada segundo, en metros cúbicos por segundo. Un metro cúbico son mil litros.'],
  ['Lluvia', 'Los litros de agua caídos por cada metro cuadrado de suelo. Un litro por metro cuadrado es lo mismo que un milímetro.'],
  ['Embalse', 'Qué parte del embalse está llena. Si se llena, guarda agua y suaviza la crecida; si se vacía, está soltando más de la que entra.'],
  ['Umbrales', 'Los niveles de aviso (amarillo, naranja y rojo) los fija el organismo oficial de cada cuenca. Si no los publica, aquí no se inventan.'],
  ['Dato antiguo', 'Si una estación lleva más de 60 minutos sin mandar lecturas, se avisa y no se presenta como situación actual.'],
];

/** Guía "qué mide cada sensor", sin tecnicismos. */
export default function SensorGuide() {
  return (
    <details className="rounded-xl border border-slate-700 bg-slate-800/60 p-3">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-bold text-slate-100">
        <BookOpen aria-hidden="true" className="h-4 w-4" />
        Qué mide cada sensor
      </summary>
      <dl className="mt-2 space-y-2 text-sm">
        {ITEMS.map(([term, text]) => (
          <div key={term}>
            <dt className="font-bold text-slate-100">{term}</dt>
            <dd className="text-slate-300">{text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
