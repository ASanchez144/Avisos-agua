import { describe, expect, it } from 'vitest';
import { STATUS, statusMeta, worstStatus } from '../lib/status.js';

describe('SIN_UMBRAL', () => {
  it('es un gris distinto de SIN_DATOS, con texto propio', () => {
    expect(STATUS.SIN_UMBRAL.color).not.toBe(STATUS.SIN_DATOS.color);
    expect(STATUS.SIN_UMBRAL.label).toBe('Umbral no publicado');
  });
  it('un estado null o desconocido NUNCA pinta semáforo (ni verde ni amarillo ni rojo)', () => {
    for (const s of [null, undefined, 'LOQUESEA']) {
      expect(statusMeta(s)).toBe(STATUS.SIN_UMBRAL);
      expect(['#22c55e', '#facc15', '#fb923c', '#ef4444']).not.toContain(statusMeta(s).color);
    }
  });
});

describe('worstStatus (color de un grupo de marcadores)', () => {
  it('lo más grave manda', () => expect(worstStatus(['NORMAL', 'ALERTA', 'VIGILANCIA'])).toBe('ALERTA'));
  it('un grupo solo es verde si TODAS están normales', () => {
    expect(worstStatus(['NORMAL', 'NORMAL'])).toBe('NORMAL');
    expect(worstStatus(['NORMAL', 'SIN_DATOS'])).toBe('SIN_DATOS');
    expect(worstStatus(['NORMAL', 'DATO_OBSOLETO'])).toBe('DATO_OBSOLETO');
    expect(worstStatus(['NORMAL', null])).toBe('SIN_UMBRAL');
  });
  it('las alertas ganan a la falta de datos', () => expect(worstStatus(['SIN_DATOS', 'PREALERTA'])).toBe('PREALERTA'));
  it('vacío no inventa', () => expect(worstStatus([])).toBe('SIN_DATOS'));
});

import { ringGradient, statusBreakdown, worstAlert } from '../lib/status.js';

describe('grupos de marcadores', () => {
  it('reparte los estados en orden fijo y cuenta los desconocidos como sin umbral', () => {
    expect(statusBreakdown(['NORMAL', 'NORMAL', 'DATO_OBSOLETO', null])).toEqual([
      { status: 'NORMAL', count: 2 }, { status: 'SIN_UMBRAL', count: 1 }, { status: 'DATO_OBSOLETO', count: 1 },
    ]);
  });
  it('el anillo cubre 360 grados con los colores de cada estado', () => {
    const g = ringGradient(['NORMAL', 'NORMAL', 'NORMAL', 'DATO_OBSOLETO']);
    expect(g).toBe('conic-gradient(#22c55e 0.0deg 270.0deg, #78716c 270.0deg 360.0deg)');
  });
  it('el centro solo destaca avisos; sin umbral o dato antiguo no cuentan como aviso', () => {
    expect(worstAlert(['NORMAL', 'SIN_UMBRAL', 'DATO_OBSOLETO'])).toBeNull();
    expect(worstAlert(['NORMAL', 'VIGILANCIA', 'ALERTA'])).toBe('ALERTA');
  });
});
