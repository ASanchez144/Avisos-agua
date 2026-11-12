import { describe, expect, it } from 'vitest';
import { APP_NAME, APP_TAGLINE } from '../lib/brand.js';
import { cameraCount, filterStations } from '../lib/stations.js';

const S = [
  { station_id: 'saih_cantabrico:1424', source: 'saih_cantabrico', has_camera: true },
  { station_id: 'saih_cantabrico:1426', source: 'saih_cantabrico', has_camera: false },
  { station_id: 'aca:1', source: 'aca', has_camera: false },
  { station_id: 'aemet:1', source: 'aemet', has_camera: false },
];

describe('filterStations', () => {
  it('por defecto oculta los pluviómetros de AEMET', () => {
    expect(filterStations(S, {}).map((s) => s.station_id)).toEqual(['saih_cantabrico:1424', 'saih_cantabrico:1426', 'aca:1']);
  });
  it('con pluviómetros los enseña', () => expect(filterStations(S, { showRain: true })).toHaveLength(4));
  it('solo con cámara', () => expect(filterStations(S, { onlyCameras: true }).map((s) => s.station_id)).toEqual(['saih_cantabrico:1424']));
  it('cuenta cámaras', () => expect(cameraCount(S)).toBe(1));
});

describe('marca', () => {
  it('nombre y lema en un solo sitio', () => {
    expect(APP_NAME).toBe('Aguas Arriba');
    expect(APP_TAGLINE).toMatch(/ríos/i);
  });
});
