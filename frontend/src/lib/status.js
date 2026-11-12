import { AlertOctagon, AlertTriangle, CheckCircle2, Clock, Eye, HelpCircle, WifiOff } from 'lucide-react';

// Cada estado lleva color + icono + texto: nunca solo color (accesibilidad).
export const STATUS = {
  NORMAL: { label: 'Normal', short: 'OK', color: '#22c55e', text: '#052e16', Icon: CheckCircle2, help: 'Por debajo de los umbrales oficiales de aviso.' },
  VIGILANCIA: { label: 'Vigilancia', short: 'V', color: '#facc15', text: '#422006', Icon: Eye, help: 'Ha superado el umbral oficial amarillo.' },
  PREALERTA: { label: 'Prealerta', short: 'P', color: '#fb923c', text: '#431407', Icon: AlertTriangle, help: 'Ha superado el umbral oficial naranja.' },
  ALERTA: { label: 'Alerta', short: 'A', color: '#ef4444', text: '#ffffff', Icon: AlertOctagon, help: 'Ha superado el umbral oficial rojo.' },
  SIN_DATOS: { label: 'Sin datos', short: '—', color: '#6b7280', text: '#ffffff', Icon: WifiOff, help: 'La estación o su fuente no están dando datos fiables ahora.' },
  DATO_OBSOLETO: { label: 'Dato antiguo', short: '⏱', color: '#6b7280', text: '#ffffff', Icon: Clock, help: 'Hace más de 60 minutos que no llega una lectura nueva.' },
  SIN_UMBRAL: { label: 'Umbral no publicado', short: '?', color: '#38bdf8', text: '#082f49', Icon: HelpCircle, help: 'Hay dato, pero la fuente oficial no publica umbrales: no se calcula semáforo.' },
};

export function statusMeta(status) {
  return STATUS[status] || STATUS.SIN_UMBRAL;
}

export const WARNING_COLORS = { amarillo: '#facc15', naranja: '#fb923c', rojo: '#ef4444' };
