import { CloudRain, Info, Siren, Waves, WifiOff } from 'lucide-react';
import { etaRangeText } from '../lib/format.js';

const triggerText = (t) =>
  t?.type === 'lluvia'
    ? `lluvia intensa (${String(t.value).replace('.', ',')} litros por metro cuadrado en una hora)`
    : 'subida rápida del caudal';

function Propagation({ estimate }) {
  return (
    <li className="leading-snug">
      <strong>{estimate.destination.name}</strong>: llegada estimada {etaRangeText(estimate.eta_hours_min, estimate.eta_hours_max)}
      {' '}por {triggerText(estimate.trigger)} en {estimate.origin.name}.{' '}
      <span className="whitespace-nowrap rounded bg-black/30 px-1.5 py-0.5 text-xs font-bold">{estimate.label}</span>{' '}
      {estimate.distance_status === 'ESTIMADA' && (
        <span className="whitespace-nowrap rounded bg-black/30 px-1.5 py-0.5 text-xs font-bold">distancia ESTIMADA</span>
      )}
    </li>
  );
}

function weatherLine(weather) {
  if (!weather || weather.status !== 'OK') return 'Avisos de AEMET: sin datos ahora mismo. Consulta aemet.es.';
  if (!weather.items.length) return 'AEMET no tiene avisos vigentes en este momento.';
  const order = ['rojo', 'naranja', 'amarillo'];
  const top = order.find((level) => weather.items.some((w) => w.level === level));
  const n = weather.items.length;
  return `${n} ${n === 1 ? 'aviso' : 'avisos'} de AEMET ${n === 1 ? 'vigente' : 'vigentes'} (nivel máximo: ${top}).`;
}

/** Banner superior de alerta temprana, en lenguaje claro y con rangos horarios. */
export default function AlertBanner({ alerts, error = false }) {
  if (error || !alerts) {
    return (
      <div role="alert" className="flex items-start gap-2 bg-slate-700 px-3 py-2 text-sm font-semibold text-white">
        <WifiOff aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
        <span>SIN DATOS: no se puede conectar con el servidor. Lo que veas puede no estar actualizado.</span>
      </div>
    );
  }
  const { propagation = [], station_alerts: stationAlerts = [], weather_warnings: weather } = alerts;
  const hasWeather = weather?.status === 'OK' && weather.items.length > 0;
  const active = propagation.length > 0 || stationAlerts.length > 0 || hasWeather;
  const redWarning = hasWeather && weather.items.some((w) => w.level === 'rojo');
  const worst = stationAlerts.some((s) => s.status === 'ALERTA') || propagation.length > 0 || redWarning;

  if (!active) {
    return (
      <div role="status" className="flex items-start gap-2 bg-slate-800 px-3 py-2 text-sm text-slate-200">
        <Info aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-semibold">No hay alertas tempranas activas en las estaciones vigiladas.</p>
          <p className="text-slate-400">Esto no garantiza que no haya riesgo. {weatherLine(weather)}</p>
        </div>
      </div>
    );
  }
  return (
    <div role="alert" className={`px-3 py-2 text-sm ${worst ? 'bg-red-700 text-white' : 'bg-amber-500 text-slate-950'}`}>
      <div className="flex items-start gap-2">
        <Siren aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0" />
        <div className="min-w-0 space-y-1">
          {propagation.length > 0 && (
            <>
              <p className="text-base font-extrabold leading-tight">Alerta temprana: el agua puede llegar río abajo</p>
              <ul className="list-disc pl-4">
                <Propagation estimate={propagation[0]} />
              </ul>
              {propagation.length > 1 && (
                <details>
                  <summary className="cursor-pointer font-bold underline">
                    Ver {propagation.length - 1} {propagation.length === 2 ? 'tramo más' : 'tramos más'}
                  </summary>
                  <ul className="mt-1 list-disc space-y-1 pl-4">
                    {propagation.slice(1).map((e) => <Propagation key={e.link_id} estimate={e} />)}
                  </ul>
                </details>
              )}
            </>
          )}
          <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs sm:text-sm">
            {stationAlerts.length > 0 && (
              <span className="flex items-center gap-1 font-bold">
                <Waves aria-hidden="true" className="h-4 w-4 shrink-0" />
                {stationAlerts.length} {stationAlerts.length === 1 ? 'estación' : 'estaciones'} por encima de un umbral oficial de aviso.
              </span>
            )}
            <span className="flex items-center gap-1">
              <CloudRain aria-hidden="true" className="h-4 w-4 shrink-0" />
              {weatherLine(weather)}
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
