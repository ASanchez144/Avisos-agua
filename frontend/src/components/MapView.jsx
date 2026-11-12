import L from 'leaflet';
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import { useEffect, useMemo } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MapContainer, Polygon, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { etaRangeText } from '../lib/format.js';
import { statusMeta, WARNING_COLORS, worstStatus } from '../lib/status.js';

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

function clusterIcon(cluster) {
  const statuses = cluster.getAllChildMarkers().map((m) => m.options.status);
  const worst = worstStatus(statuses);
  const meta = statusMeta(worst);
  const html = `<div class="hr-marker hr-cluster" style="background:${meta.color};color:${meta.text}">${renderToStaticMarkup(
    <meta.Icon aria-hidden="true" />,
  )}<span>${statuses.length}</span></div>`;
  return L.divIcon({ html, className: '', iconSize: [40, 40], iconAnchor: [20, 20] });
}

function clusterTitle(cluster) {
  const counts = {};
  cluster.getAllChildMarkers().forEach((m) => {
    const label = statusMeta(m.options.status).label;
    counts[label] = (counts[label] || 0) + 1;
  });
  const parts = Object.entries(counts).map(([label, n]) => `${n} ${label.toLowerCase()}`);
  return `${cluster.getChildCount()} estaciones: ${parts.join(', ')} (peor estado: ${statusMeta(worstStatus(cluster.getAllChildMarkers().map((m) => m.options.status))).label})`;
}

/** Marcadores agrupados (markercluster). El grupo toma el color del PEOR estado de sus estaciones. */
function ClusterLayer({ stations, selectedId, onSelect }) {
  const map = useMap();
  useEffect(() => {
    const group = L.markerClusterGroup({ maxClusterRadius: 45, showCoverageOnHover: false, iconCreateFunction: clusterIcon, chunkedLoading: true });
    stations.filter(hasCoords).forEach((s) => {
      const meta = statusMeta(s.status);
      const label = `${s.name}: ${meta.label}`;
      const marker = L.marker([s.lat, s.lon], {
        icon: icon(s.status, s.station_id === selectedId), title: label, alt: label, status: s.status,
        zIndexOffset: s.station_id === selectedId ? 1000 : s.status === 'ALERTA' ? 500 : 0,
      });
      marker.bindTooltip(label, { direction: 'top', offset: [0, -14] });
      marker.on('click', () => onSelect(s.station_id));
      group.addLayer(marker);
    });
    group.on('clustermouseover', (e) => e.layer.bindTooltip(clusterTitle(e.layer)).openTooltip());
    map.addLayer(group);
    return () => { map.removeLayer(group); };
  }, [map, stations, selectedId]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

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
      <ClusterLayer stations={stations} selectedId={selectedId} onSelect={onSelect} />
    </MapContainer>
  );
}
