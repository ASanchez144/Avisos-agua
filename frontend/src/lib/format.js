// Funciones puras de presentación. Ninguna inventa datos: sin valor, lo dicen.

const nf = (digits = 0) => new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits, minimumFractionDigits: 0 });

export function num(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(value) ? '—' : nf(digits).format(value);
}

const hoursText = (h) => (Number.isInteger(h) ? String(h) : String(h).replace('.', ','));

/** Rango de llegada en lenguaje claro. Redondea SIEMPRE hacia fuera (no estrecha el rango). */
export function etaRangeText(minHours, maxHours) {
  if (minHours == null || maxHours == null) return 'sin estimación';
  const minMinutes = Math.floor((minHours * 60) / 5) * 5;
  const maxMinutes = Math.ceil((maxHours * 60) / 5) * 5;
  const lo = Math.floor(minHours * 2) / 2;
  const hi = Math.ceil(maxHours * 2) / 2;
  if (maxHours < 1) return `entre ${minMinutes} y ${maxMinutes} minutos`;
  const unit = hi === 1 ? 'hora' : 'horas';
  if (minHours < 1) return `entre ${minMinutes} minutos y ${hoursText(hi)} ${unit}`;
  return `entre ${hoursText(lo)} y ${hoursText(hi)} ${unit}`;
}

/** "hace 12 min". stale = más de 60 min (dato antiguo) o sin fecha. */
export function freshness(timestampUtc, now = new Date()) {
  if (!timestampUtc) return { text: 'sin fecha de medida', minutes: null, stale: true };
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(timestampUtc).getTime()) / 60000));
  let text;
  if (minutes < 1) text = 'hace menos de 1 min';
  else if (minutes < 60) text = `hace ${minutes} min`;
  else if (minutes < 24 * 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    text = m ? `hace ${h} h ${m} min` : `hace ${h} h`;
  } else {
    const d = Math.floor(minutes / (24 * 60));
    text = `hace ${d} ${d === 1 ? 'día' : 'días'}`;
  }
  return { text, minutes, stale: minutes > 60 };
}

export const OLYMPIC_POOL_M3 = 2500;

/** m³/s → litros por segundo y piscinas olímpicas (2.500 m³) por minuto. */
export function flowEquivalences(flowM3s) {
  if (flowM3s == null) return null;
  return { litersPerSecond: flowM3s * 1000, poolsPerMinute: (flowM3s * 60) / OLYMPIC_POOL_M3 };
}

/** Margen hasta el siguiente umbral OFICIAL por encima del valor actual. */
export function freeMargin(value, thresholds) {
  if (!thresholds || value == null) return null;
  for (const key of ['yellow', 'orange', 'red']) {
    const limit = thresholds[key];
    if (limit != null && value < limit) return { next: key, margin: Math.round((limit - value) * 100) / 100 };
  }
  return { next: null, margin: 0 };
}

/** ¿El embalse guarda agua (amortigua) o la suelta? Solo con histórico; si no, no opina. */
export function reservoirTrend(historyDesc) {
  const points = (historyDesc || []).filter((r) => r.reservoir_hm3 != null && r.timestamp_utc);
  if (points.length < 2) return { kind: 'desconocido', deltaHm3: null, hours: null };
  const latest = points[0];
  const windowStart = new Date(latest.timestamp_utc).getTime() - 3 * 3600 * 1000;
  const inWindow = points.filter((p) => new Date(p.timestamp_utc).getTime() >= windowStart);
  const oldest = inWindow[inWindow.length - 1];
  if (oldest === latest) return { kind: 'desconocido', deltaHm3: null, hours: null };
  const delta = latest.reservoir_hm3 - oldest.reservoir_hm3;
  const hours = (new Date(latest.timestamp_utc) - new Date(oldest.timestamp_utc)) / 3600000;
  const noise = Math.max(0.005, Math.abs(latest.reservoir_hm3) * 0.0005);
  const kind = Math.abs(delta) <= noise ? 'estable' : delta > 0 ? 'guarda' : 'suelta';
  return { kind, deltaHm3: Math.round(delta * 100) / 100, hours: Math.round(hours * 10) / 10 };
}

export const THRESHOLD_NAMES = { yellow: 'aviso amarillo', orange: 'aviso naranja', red: 'aviso rojo' };
