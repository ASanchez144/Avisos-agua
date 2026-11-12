import L from 'leaflet';
import { useEffect, useMemo } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MapContainer, Marker, Polygon, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { etaRangeText } from '../lib/format.js';
import { statusMeta, WARNING_COLORS } from '../lib/status.js';

const SPAIN = [[35.8, -9.6], [43.9, 4.4]];
const SHAPE = { SIN_DATOS: 'hr-square', DATO_OBSOLETO: 'hr-square', SIN_UMBRAL: 'hr-diamond' };

function icon(status, selected) {
  const meta = statusMeta(status);
  const shape = SHAPE[status ?? 'SIN_UMBRAL'] || '';
  const size = selected ? 38 : 30;
  // Color + icono + letra + forma: el estado no depende solo del color.
  const html = `<div class="hr-marker ${shape} ${selected ? 'hr-selected' : ''}" style="background:${meta.color};color:${meta.text}">${renderToStaticMarkup(
    <meta.Icon aria-hidden="true" />,
  )}<span>${meta.short}</span></div>`;
  return L.divIcon({ html, className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

function FitToStations({ stations }) {
  const map = useMap();
  const key = stations.length ? `${stations.length}:${stations[0].station_id}` : '';
  useEffect(() => {
    const points = stations.filter((s) => s.lat != null && s.lon != null).map((s) => [s.lat, s.lon]);
    if (points.length) map.fitBounds(L.latLngBounds(points).pad(0.15), { maxZoom: 11 });
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

const hasCoords = (p) => p && p.lat != null && p.lon != null;

/** Mapa: marcadores por estado, líneas discontinuas de propagación y zonas con aviso AEMET. */
export default function MapView({ stations, links = [], active = [], warnings = [], selectedId, onSelect }) {
  const activeById = useMemo(() => Object.fromEntries(active.map((e) => [e.link_id, e])), [active]);
  return (
    <MapContainer bounds={SPAIN} className="h-full w-full" zoomControl={false} attributionControl>
      <TileLayer
        className="hr-tiles"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      <FitToStations stations={stations} />
      {warnings.flatMap((w) =>
        (w.polygons || []).map((polygon, i) => (
          <Polygon key={`${w.identifier}-${i}`} positions={polygon}
            pathOptions={{ color: WARNING_COLORS[w.level] || '#94a3b8', weight: 1, fillOpacity: 0.12, dashArray: '2 4' }}>
            <Tooltip sticky>{w.headline || w.event} (AEMET)</Tooltip>
          </Polygon>
        )),
      )}
      {links.filter((l) => hasCoords(l.origin) && hasCoords(l.destination)).map((l) => {
        const estimate = activeById[l.link_id];
        return (
          <Polyline key={l.link_id}
            positions={[[l.origin.lat, l.origin.lon], [l.destination.lat, l.destination.lon]]}
            pathOptions={{ color: estimate ? '#f97316' : '#94a3b8', weight: estimate ? 5 : 2, dashArray: estimate ? '10 8' : '4 8', opacity: estimate ? 1 : 0.7 }}>
            <Tooltip sticky>
              {l.origin.name} → {l.destination.name}.{' '}
              {estimate
                ? `Llegada estimada ${etaRangeText(estimate.eta_hours_min, estimate.eta_hours_max)}`
                : `Si hubiera crecida tardaría ${etaRangeText(l.eta_hours_min, l.eta_hours_max)}`}
              {' '}({l.label}; distancia {l.distance_status}).
            </Tooltip>
          </Polyline>
        );
      })}
      {stations.filter(hasCoords).map((s) => {
        const meta = statusMeta(s.status);
        const label = `${s.name}: ${meta.label}`;
        return (
          <Marker key={s.station_id} position={[s.lat, s.lon]} icon={icon(s.status, s.station_id === selectedId)}
            title={label} alt={label} zIndexOffset={s.station_id === selectedId ? 1000 : s.status === 'ALERTA' ? 500 : 0}
            eventHandlers={{ click: () => onSelect(s.station_id), keypress: (e) => e.originalEvent.key === 'Enter' && onSelect(s.station_id) }}>
            <Tooltip direction="top" offset={[0, -14]}>{label}</Tooltip>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
