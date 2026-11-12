import { AlertOctagon, AlertTriangle, CheckCircle2, Clock, Eye, HelpCircle, WifiOff } from 'lucide-react';

// Cada estado lleva color + icono + texto: nunca solo color (accesibilidad).
export const STATUS = {
  NORMAL: { label: 'Normal', short: 'OK', color: '#22c55e', text: '#052e16', Icon: CheckCircle2, help: 'Por debajo de los umbrales oficiales de aviso.' },
  VIGILANCIA: { label: 'Vigilancia', short: 'V', color: '#facc15', text: '#422006', Icon: Eye, help: 'Ha superado el umbral oficial amarillo.' },
  PREALERTA: { label: 'Prealerta', short: 'P', color: '#fb923c', text: '#431407', Icon: AlertTriangle, help: 'Ha superado el umbral oficial naranja.' },
  ALERTA: { label: 'Alerta', short: 'A', color: '#ef4444', text: '#ffffff', Icon: AlertOctagon, help: 'Ha superado el umbral oficial rojo.' },
  SIN_DATOS: { label: 'Sin datos', short: '—', color: '#4b5563', text: '#ffffff', Icon: WifiOff, help: 'La estación o su fuente no están dando datos fiables ahora.' },
  DATO_OBSOLETO: { label: 'Dato antiguo', short: '⏱', color: '#78716c', text: '#ffffff', Icon: Clock, help: 'Hace más de 60 minutos que no llega una lectura nueva.' },
  SIN_UMBRAL: { label: 'Umbral no publicado', short: '?', color: '#cbd5e1', text: '#0f172a', Icon: HelpCircle, help: 'Hay dato, pero la fuente oficial no publica umbrales: no se calcula semáforo.' },
};

/** Un estado null o desconocido nunca pinta semáforo: cae en SIN_UMBRAL (gris claro, distinto de SIN_DATOS). */
export function statusMeta(status) {
  return STATUS[status] || STATUS.SIN_UMBRAL;
}

// De peor a mejor para un GRUPO de marcadores: las alertas primero; después lo que no se puede
// fiar (sin datos, dato antiguo, sin umbral); verde solo si todas las estaciones están normales.
const WORST_FIRST = ['ALERTA', 'PREALERTA', 'VIGILANCIA', 'SIN_DATOS', 'DATO_OBSOLETO', 'SIN_UMBRAL', 'NORMAL'];

export function worstStatus(statuses) {
  if (!statuses.length) return 'SIN_DATOS';
  const normalized = statuses.map((s) => (STATUS[s] ? s : 'SIN_UMBRAL'));
  return WORST_FIRST.find((s) => normalized.includes(s));
}

export const WARNING_COLORS = { amarillo: '#facc15', naranja: '#fb923c', rojo: '#ef4444' };

const RING_ORDER = ['ALERTA', 'PREALERTA', 'VIGILANCIA', 'NORMAL', 'SIN_UMBRAL', 'DATO_OBSOLETO', 'SIN_DATOS'];
const ALERT_LEVELS = ['ALERTA', 'PREALERTA', 'VIGILANCIA'];

/** Reparto de estados de un grupo, en orden fijo: [{ status, count }]. */
export function statusBreakdown(statuses) {
  const normalized = statuses.map((s) => (STATUS[s] ? s : 'SIN_UMBRAL'));
  return RING_ORDER.map((status) => ({ status, count: normalized.filter((s) => s === status).length })).filter((p) => p.count);
}

/** Anillo proporcional (conic-gradient) con el color de cada estado del grupo. */
export function ringGradient(statuses) {
  const parts = statusBreakdown(statuses);
  const total = parts.reduce((n, p) => n + p.count, 0) || 1;
  let acc = 0;
  const stops = parts.map((p) => {
    const from = (acc / total) * 360;
    acc += p.count;
    return `${STATUS[p.status].color} ${from.toFixed(1)}deg ${((acc / total) * 360).toFixed(1)}deg`;
  });
  return `conic-gradient(${stops.join(', ')})`;
}

/** Peor nivel de AVISO del grupo (alerta > prealerta > vigilancia) o null si no hay ninguno. */
export function worstAlert(statuses) {
  return ALERT_LEVELS.find((s) => statuses.includes(s)) || null;
}
