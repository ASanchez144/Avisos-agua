import { ArrowDownToLine, ArrowUpFromLine, CloudRain, Container, Droplets, Equal, Ruler, WifiOff, X } from 'lucide-react';
import { flowEquivalences, num, reservoirTrend } from '../lib/format.js';
import { statusMeta } from '../lib/status.js';
import DemoBadge from './DemoBadge.jsx';
import CameraView from './CameraView.jsx';
import Freshness from './Freshness.jsx';
import Hydrograph from './Hydrograph.jsx';
import LevelBar from './LevelBar.jsx';
import SensorGuide from './SensorGuide.jsx';

function Card({ icon: Icon, title, children }) {
  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800/60 p-3">
      <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-300">
        <Icon aria-hidden="true" className="h-4 w-4" />
        {title}
      </h3>
      {children}
    </section>
  );
}

const Big = ({ children }) => <p className="mt-1 text-2xl font-extrabold text-white">{children}</p>;

const TREND = {
  guarda: [ArrowDownToLine, 'Está guardando agua: entra más de la que sale, así que amortigua la crecida.'],
  suelta: [ArrowUpFromLine, 'Está soltando agua: sale más de la que entra.'],
  estable: [Equal, 'Se mantiene estable: entra y sale más o menos la misma agua.'],
  desconocido: [Equal, 'Aún no hay histórico suficiente para saber si guarda o suelta agua.'],
};

function pools(value) {
  return num(value, value >= 10 ? 0 : value >= 1 ? 1 : 2);
}

export default function StationPanel({ station, history, now = new Date(), demo = false, onClose }) {
  const meta = statusMeta(station.status);
  const latest = station.latest;
  const noData = station.status === 'SIN_DATOS' || !latest || latest.quality === 'MISSING';
  const obsolete = station.status === 'DATO_OBSOLETO';
  const th = latest?.thresholds || null;
  const eq = flowEquivalences(latest?.flow_m3s);
  const trend = reservoirTrend(history);
  const [TrendIcon, trendText] = TREND[trend.kind];

  return (
    <section role="region" aria-label={`Estación ${station.name}`} className="flex h-full flex-col bg-slate-900">
      {demo && <DemoBadge compact />}
      <header className="flex items-start gap-2 border-b border-slate-700 p-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-extrabold leading-tight text-white">{station.name}</h2>
          {station.river && <p className="text-sm text-slate-400">{station.river}</p>}
          <p className="mt-1.5 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-extrabold"
            style={{ background: meta.color, color: meta.text }} title={meta.help}>
            <meta.Icon aria-hidden="true" className="h-4 w-4" />
            <span>{meta.label}</span>
          </p>
          <p className="mt-1 text-xs text-slate-400">{meta.help}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Cerrar panel de estación"
          className="rounded-lg border border-slate-600 p-2 text-slate-200 hover:bg-slate-800">
          <X aria-hidden="true" className="h-5 w-5" />
        </button>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {noData ? (
          <p role="alert" className="flex items-start gap-2 rounded-lg border border-slate-500 bg-slate-800 p-3 text-sm font-semibold text-slate-100">
            <WifiOff aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
            <span>Sin datos: esta estación o su fuente no están dando lecturas fiables ahora mismo. No se muestra ningún valor.</span>
          </p>
        ) : (
          <>
            <Freshness timestamp={latest.timestamp_utc} now={now} limitMinutes={station.fresh_limit_minutes ?? 60} />
            {obsolete && <p className="text-sm font-bold uppercase tracking-wide text-amber-200">Última lectura conocida (no es la situación actual)</p>}
            {latest.quality === 'SUSPECT' && (
              <p className="rounded-lg border border-slate-500 bg-slate-800 p-2 text-sm text-slate-200">
                Esta lectura tiene algún valor poco creíble. Se enseña tal cual, pero no se usa para alertas.
              </p>
            )}
            <div className={`space-y-3 ${obsolete ? 'opacity-60' : ''}`}>
              {latest.level_m != null && (
                <Card icon={Ruler} title="Nivel del agua">
                  <Big>{num(latest.level_m)} m</Big>
                  <LevelBar value={latest.level_m} thresholds={th?.variable === 'level_m' ? th : null} unit="m" />
                </Card>
              )}
              {latest.flow_m3s != null && (
                <Card icon={Droplets} title="Caudal">
                  <Big>{num(latest.flow_m3s)} m³/s</Big>
                  <p className="text-sm text-slate-300">
                    Son <strong>{num(eq.litersPerSecond, 0)} litros por segundo</strong>: como llenar{' '}
                    <strong>{pools(eq.poolsPerMinute)} piscinas olímpicas por minuto</strong>.
                  </p>
                  {th?.variable === 'flow_m3s' && <LevelBar value={latest.flow_m3s} thresholds={th} unit="m³/s" />}
                </Card>
              )}
              {(latest.rain_1h_mm != null || latest.rain_24h_mm != null) && (
                <Card icon={CloudRain} title="Lluvia en este punto">
                  {latest.rain_1h_mm != null && <Big>{num(latest.rain_1h_mm, 1)} litros por metro cuadrado</Big>}
                  <p className="text-sm text-slate-300">
                    {latest.rain_1h_mm != null && 'caídos en la última hora. '}
                    {latest.rain_24h_mm != null && <>En 24 horas: <strong>{num(latest.rain_24h_mm, 1)} litros por metro cuadrado</strong>.</>}
                  </p>
                </Card>
              )}
              {(latest.reservoir_pct != null || latest.reservoir_hm3 != null) && (
                <Card icon={Container} title="Embalse">
                  {latest.reservoir_pct != null && (
                    <>
                      <p className="mt-1 text-2xl font-extrabold text-white"><strong>{num(latest.reservoir_pct, 1)} % lleno</strong></p>
                      <div className="mt-1 h-4 w-full rounded-full bg-slate-700" aria-hidden="true">
                        <div className="h-4 rounded-full bg-sky-400" style={{ width: `${Math.max(0, Math.min(100, latest.reservoir_pct))}%` }} />
                      </div>
                    </>
                  )}
                  {latest.reservoir_hm3 != null && <p className="mt-1 text-sm text-slate-300">Agua guardada: {num(latest.reservoir_hm3, 1)} hm³ (un hm³ son mil millones de litros).</p>}
                  <p className="mt-1.5 flex items-start gap-1.5 text-sm font-semibold text-slate-100">
                    <TrendIcon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{trendText}</span>
                  </p>
                </Card>
              )}
              <Card icon={Droplets} title="Lluvia y caudal en las últimas horas">
                <div className="mt-2"><Hydrograph history={history} /></div>
              </Card>
            </div>
          </>
        )}
        {!demo && <CameraView stationId={station.station_id} now={now} />}
        <SensorGuide />
        <p className="text-xs text-slate-500">Fuente del dato: {station.source}. Identificador: {station.station_id}.</p>
      </div>
    </section>
  );
}
