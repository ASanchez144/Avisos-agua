import { describe, expect, it } from 'vitest';
import { etaRangeText, flowEquivalences, freshness, freeMargin, reservoirTrend } from '../lib/format.js';

describe('etaRangeText: siempre un rango, nunca una hora exacta', () => {
  it('horas enteras', () => expect(etaRangeText(3, 5)).toBe('entre 3 y 5 horas'));
  it('redondea hacia fuera a medias horas', () => expect(etaRangeText(3.36, 7.85)).toBe('entre 3 y 8 horas'));
  it('medias horas con coma', () => expect(etaRangeText(1.4, 3.27)).toBe('entre 1 y 3,5 horas'));
  it('todo en minutos si es menos de una hora', () => expect(etaRangeText(0.52, 0.9)).toBe('entre 30 y 55 minutos'));
  it('mezcla minutos y horas', () => expect(etaRangeText(0.7, 1.4)).toBe('entre 40 minutos y 1,5 horas'));
  it('sin datos no inventa', () => expect(etaRangeText(null, 2)).toBe('sin estimación'));
});

describe('freshness', () => {
  const now = new Date('2026-11-11T12:00:00Z');
  it('minutos', () => expect(freshness('2026-11-11T11:48:00Z', now)).toEqual({ text: 'hace 12 min', minutes: 12, stale: false }));
  it('recién llegado', () => expect(freshness('2026-11-11T11:59:40Z', now).text).toBe('hace menos de 1 min'));
  it('más de 60 min es dato antiguo', () => expect(freshness('2026-11-11T10:30:00Z', now)).toEqual({ text: 'hace 1 h 30 min', minutes: 90, stale: true }));
  it('días', () => expect(freshness('2026-11-08T12:00:00Z', now).text).toBe('hace 3 días'));
  it('sin fecha', () => expect(freshness(null, now)).toEqual({ text: 'sin fecha de medida', minutes: null, stale: true }));
});

describe('flowEquivalences', () => {
  it('pasa m³/s a litros por segundo y piscinas olímpicas por minuto', () => {
    expect(flowEquivalences(125)).toEqual({ litersPerSecond: 125000, poolsPerMinute: 3 });
  });
  it('caudal pequeño', () => expect(flowEquivalences(0.75).poolsPerMinute).toBeCloseTo(0.018, 3));
  it('sin dato', () => expect(flowEquivalences(null)).toBeNull());
});

describe('freeMargin: margen hasta el siguiente umbral oficial', () => {
  const th = { yellow: 2, orange: 3, red: 4, variable: 'level_m' };
  it('por debajo del amarillo', () => expect(freeMargin(1.4, th)).toEqual({ next: 'yellow', margin: 0.6 }));
  it('entre amarillo y naranja', () => expect(freeMargin(2.5, th)).toEqual({ next: 'orange', margin: 0.5 }));
  it('por encima del rojo', () => expect(freeMargin(4.3, th)).toEqual({ next: null, margin: 0 }));
  it('umbrales parciales', () => expect(freeMargin(2.5, { yellow: 2, orange: null, red: null })).toEqual({ next: null, margin: 0 }));
  it('sin umbrales', () => expect(freeMargin(1, null)).toBeNull());
});

describe('reservoirTrend', () => {
  const r = (t, hm3) => ({ timestamp_utc: t, reservoir_hm3: hm3 });
  it('sube: guarda agua', () => expect(reservoirTrend([r('2026-11-11T12:00:00Z', 142), r('2026-11-11T10:00:00Z', 140.6)]).kind).toBe('guarda'));
  it('baja: suelta agua', () => expect(reservoirTrend([r('2026-11-11T12:00:00Z', 140), r('2026-11-11T10:00:00Z', 141)]).kind).toBe('suelta'));
  it('estable', () => expect(reservoirTrend([r('2026-11-11T12:00:00Z', 140.001), r('2026-11-11T10:00:00Z', 140)]).kind).toBe('estable'));
  it('sin histórico no opina', () => expect(reservoirTrend([r('2026-11-11T12:00:00Z', 140)]).kind).toBe('desconocido'));
});
