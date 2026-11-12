import { Camera, CameraOff, ExternalLink } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { freshness, num } from '../lib/format.js';

const MIN_REFRESH_S = 60;
const MAX_REFRESH_S = 180;

/**
 * Cámara de tráfico cercana, SOLO para ver. La imagen se enlaza directamente desde su origen
 * (hotlink): no se descarga, no se guarda y no se analiza. Se enseña solo si la API dice que está
 * al día; si no, "Cámara sin señal" (nunca una imagen vieja como si fuera actual).
 */
export default function CameraView({ stationId, now = new Date() }) {
  const [state, setState] = useState({ phase: 'cargando' });
  const [tick, setTick] = useState(() => Date.now());
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer;
    const load = async () => {
      try {
        const body = await api.camera(stationId);
        if (cancelled) return;
        setImageFailed(false);
        setTick(Date.now());
        setState(body.camera ? { phase: 'camara', camera: body.camera } : { phase: 'ninguna', reason: body.reason });
        const seconds = Math.min(MAX_REFRESH_S, Math.max(MIN_REFRESH_S, body.camera?.refresh_seconds ?? 120));
        timer = setTimeout(load, seconds * 1000);
      } catch {
        if (cancelled) return;
        setState({ phase: 'error' });
        timer = setTimeout(load, 120 * 1000);
      }
    };
    setState({ phase: 'cargando' });
    load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [stationId]);

  const header = (
    <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-300">
      <Camera aria-hidden="true" className="h-4 w-4" />
      {state.camera?.kind === 'aforo' ? 'Cámara del río' : 'Cámara cercana'}
    </h3>
  );
  if (state.phase === 'cargando') return null;
  if (state.phase === 'ninguna') {
    return (
      <section className="rounded-xl border border-slate-700 bg-slate-800/60 p-3">
        {header}
        <p className="mt-1 text-sm text-slate-400">{state.reason || 'No hay ninguna cámara verificada cerca.'}</p>
      </section>
    );
  }
  const cam = state.camera;
  const noSignal = state.phase === 'error' || imageFailed || cam?.status?.status !== 'OK';
  if (noSignal) {
    return (
      <section className="rounded-xl border border-slate-700 bg-slate-800/60 p-3">
        {header}
        <p role="alert" className="mt-2 flex items-start gap-2 rounded-lg border border-slate-500 bg-slate-900 p-3 text-sm font-semibold text-slate-100">
          <CameraOff aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
          <span>{cam?.status?.message || 'Cámara sin señal: no se puede comprobar la imagen.'}</span>
        </p>
        {cam && (
          <a href={cam.origin_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm text-sky-300 underline">
            Ver en el origen <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
          </a>
        )}
      </section>
    );
  }
  const age = freshness(cam.status.last_modified_utc, now, 20);
  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800/60 p-3">
      {header}
      <img
        src={`${cam.image_url}?_=${tick}`}
        alt={cam.kind === 'aforo' ? 'Imagen de la cámara oficial que enfoca el río en la estación de aforo' : 'Imagen en directo de la cámara de tráfico más cercana a la estación'}
        referrerPolicy="no-referrer"
        loading="lazy"
        onError={() => setImageFailed(true)}
        className="mt-2 w-full rounded-lg bg-black"
      />
      <p className="mt-1 text-sm text-slate-300">
        Foto {age.text}
        {cam.kind === 'aforo' ? ' · cámara oficial en la propia estación de aforo.' : ` · a ${num(cam.distance_km, 1)} km de la estación (cámara de tráfico).`}
        {' '}Solo para ver, sin análisis.
      </p>
      <a href={cam.origin_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm text-sky-300 underline">
        Ver en el origen ({cam.kind === 'aforo' ? 'CH Cantábrico' : 'DGT'}) <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
      </a>
    </section>
  );
}
