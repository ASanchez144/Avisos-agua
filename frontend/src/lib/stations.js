const RAIN_ONLY_SOURCES = new Set(['aemet']); // pluviómetros: se muestran solo si se piden

export function filterStations(stations, { showRain = false, onlyCameras = false } = {}) {
  return stations.filter((s) => (showRain || !RAIN_ONLY_SOURCES.has(s.source)) && (!onlyCameras || s.has_camera));
}

export const cameraCount = (stations) => stations.filter((s) => s.has_camera).length;
export const hasRainSources = (stations) => stations.some((s) => RAIN_ONLY_SOURCES.has(s.source));
