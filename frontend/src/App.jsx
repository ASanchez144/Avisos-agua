import { Camera, CloudRain, Waves } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';
import AlertBanner from './components/AlertBanner.jsx';
import DemoBadge from './components/DemoBadge.jsx';
import Legend from './components/Legend.jsx';
import LegalBar from './components/LegalBar.jsx';
import MapView from './components/MapView.jsx';
import StationPanel from './components/StationPanel.jsx';
import { APP_NAME } from './lib/brand.js';
import { cameraCount, filterStations, hasRainSources as anyRain } from './lib/stations.js';

const REFRESH_MS = 5 * 60 * 1000;

export default function App() {
  const [stations, setStations] = useState([]);
  const [alerts, setAlerts] = useState(null);
  const [propagation, setPropagation] = useState({ links: [], active: [] });
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [showRain, setShowRain] = useState(false);
  const [onlyCameras, setOnlyCameras] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [now, setNow] = useState(() => new Date());

  const refresh = useCallback(async () => {
    try {
      const [s, a, p] = await Promise.all([api.stations(), api.alerts(), api.propagation()]);
      setStations(s.stations);
      setAlerts(a);
      setPropagation({ links: p.links, active: p.active });
      setDemo(Boolean(s.demo));
      setError(false);
    } catch {
      // Si el servidor falla no se deja nada "en verde": se vacía y se avisa.
      setError(true);
      setStations([]);
      setAlerts(null);
      setPropagation({ links: [], active: [] });
    } finally {
      setLoaded(true);
      setNow(new Date());
    }
  }, []);

  // Respaldo del cron: si los datos tienen más de ~15 min, el servidor hace un ciclo y luego se refresca.
  const collect = useCallback(async () => {
    try {
      const r = await api.collect();
      if (r.ran) refresh();
    } catch {
      /* si falla, se siguen mostrando los datos con su edad real */
    }
  }, [refresh]);

  useEffect(() => {
    refresh();
    collect();
    const data = setInterval(() => { refresh(); collect(); }, REFRESH_MS);
    const clock = setInterval(() => setNow(new Date()), 30 * 1000);
    return () => { clearInterval(data); clearInterval(clock); };
  }, [refresh, collect]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return undefined; }
    let cancelled = false;
    Promise.all([api.station(selectedId), api.history(selectedId)])
      .then(([s, h]) => { if (!cancelled) setDetail({ station: s.station, history: h.readings }); })
      .catch(() => { if (!cancelled) setDetail({ station: stations.find((x) => x.station_id === selectedId) && { ...stations.find((x) => x.station_id === selectedId), status: 'SIN_DATOS', latest: null }, history: [] }); });
    return () => { cancelled = true; };
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  const visible = useMemo(() => filterStations(stations, { showRain, onlyCameras }), [stations, showRain, onlyCameras]);
  const hasRainSources = anyRain(stations);
  const nCameras = cameraCount(stations);

  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-100">
      {demo && <DemoBadge />}
      <header className="flex items-center gap-2 border-b border-slate-800 bg-slate-900 px-3 py-2">
        <Waves aria-hidden="true" className="h-6 w-6 text-sky-400" />
        <h1 className="text-base font-extrabold sm:text-lg">{APP_NAME}</h1>
        <span className="ml-auto text-xs text-slate-400">{loaded && !error ? `${visible.length} estaciones` : ''}</span>
      </header>
      <AlertBanner alerts={alerts} error={error} />

      <main className="relative flex min-h-0 flex-1 flex-col md:flex-row">
        <div className="relative isolate min-h-0 flex-1" aria-label="Mapa de estaciones">
          <MapView stations={visible} links={propagation.links} active={propagation.active}
            warnings={alerts?.weather_warnings?.items || []} selectedId={selectedId} onSelect={setSelectedId} />
          <div className="pointer-events-none absolute left-2 top-2 z-[1000] flex max-w-[70%] flex-col items-start gap-2">
            <div className="pointer-events-auto"><Legend /></div>
            {nCameras > 0 && (
              <label className="pointer-events-auto flex cursor-pointer items-center gap-2 rounded-xl border border-slate-600 bg-slate-900/95 px-3 py-2 text-sm font-semibold shadow-lg">
                <input type="checkbox" className="h-4 w-4" checked={onlyCameras} onChange={(e) => setOnlyCameras(e.target.checked)} />
                <Camera aria-hidden="true" className="h-4 w-4" />
                Solo con cámara del río ({nCameras})
              </label>
            )}
            {hasRainSources && (
              <label className="pointer-events-auto flex cursor-pointer items-center gap-2 rounded-xl border border-slate-600 bg-slate-900/95 px-3 py-2 text-sm font-semibold shadow-lg">
                <input type="checkbox" className="h-4 w-4" checked={showRain} onChange={(e) => setShowRain(e.target.checked)} />
                <CloudRain aria-hidden="true" className="h-4 w-4" />
                Ver pluviómetros de AEMET
              </label>
            )}
          </div>
          {loaded && !error && visible.length === 0 && (
            <p className="absolute inset-x-4 top-1/3 z-[1000] rounded-xl bg-slate-900/95 p-4 text-center font-semibold">
              SIN DATOS: todavía no ha llegado ninguna lectura de las fuentes.
            </p>
          )}
        </div>
        {detail?.station && (
          <aside className="absolute inset-x-0 bottom-0 z-10 max-h-[72%] overflow-hidden rounded-t-2xl border-t border-slate-700 shadow-2xl md:static md:max-h-none md:w-[400px] md:rounded-none md:border-l md:border-t-0">
            <StationPanel station={detail.station} history={detail.history} now={now} demo={demo} onClose={() => setSelectedId(null)} />
          </aside>
        )}
      </main>
      <LegalBar />
    </div>
  );
}
