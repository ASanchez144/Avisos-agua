import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AlertBanner from '../components/AlertBanner.jsx';
import DemoBadge from '../components/DemoBadge.jsx';
import Freshness from '../components/Freshness.jsx';
import LegalBar from '../components/LegalBar.jsx';
import LevelBar from '../components/LevelBar.jsx';
import StationPanel from '../components/StationPanel.jsx';

const NOW = new Date('2026-11-11T12:00:00Z');
const TH = { yellow: 2, orange: 3, red: 4, variable: 'level_m' };

const estimate = {
  link_id: 'x', origin: { name: 'Río Ejemplo en Cabecera' }, destination: { name: 'Río Ejemplo en Valle' },
  trigger: { type: 'lluvia', value: 26, unit: 'mm/h' }, eta_hours_min: 3, eta_hours_max: 5,
  distance_km: 40, distance_status: 'ESTIMADA', speed_status: 'ESTIMADA', label: 'estimación orientativa', via: [],
};
const quiet = { station_alerts: [], propagation: [], weather_warnings: { status: 'OK', source: 'AEMET', items: [] } };

function station(extra = {}, latest = {}) {
  return {
    station_id: 't:1', source: 't', name: 'Río Ejemplo en Ciudad', river: 'Río Ejemplo', lat: 40, lon: -3,
    status: 'NORMAL', threshold_note: null, source_ok: true,
    latest: {
      flow_m3s: 125, level_m: 1.4, rain_1h_mm: 12.5, rain_24h_mm: 40, reservoir_pct: null, reservoir_hm3: null,
      thresholds: TH, timestamp_utc: '2026-11-11T11:48:00Z', fetched_at_utc: '2026-11-11T11:50:00Z', quality: 'OK', ...latest,
    },
    ...extra,
  };
}

describe('AlertBanner', () => {
  it('explica la alerta temprana con un rango horario y la marca de estimación', () => {
    render(<AlertBanner alerts={{ ...quiet, propagation: [estimate] }} />);
    const banner = screen.getByRole('alert');
    expect(banner).toHaveTextContent('Río Ejemplo en Valle');
    expect(banner).toHaveTextContent('llegada estimada entre 3 y 5 horas');
    expect(banner).toHaveTextContent('estimación orientativa');
    expect(banner).toHaveTextContent('distancia ESTIMADA');
    expect(banner).not.toHaveTextContent(/\d{1,2}:\d{2}/); // nunca una hora exacta
  });

  it('sin alertas no promete seguridad', () => {
    render(<AlertBanner alerts={quiet} />);
    expect(screen.getByRole('status')).toHaveTextContent('No hay alertas tempranas activas');
    expect(screen.getByRole('status')).toHaveTextContent('no garantiza');
  });

  it('cuenta las estaciones por encima de umbral oficial', () => {
    render(<AlertBanner alerts={{ ...quiet, station_alerts: [{ station_id: 'a', name: 'X', status: 'ALERTA' }, { station_id: 'b', name: 'Y', status: 'VIGILANCIA' }] }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('2 estaciones por encima de un umbral oficial');
  });

  it('un aviso rojo de AEMET pinta el banner en rojo, no en ámbar', () => {
    const weather = { status: 'OK', source: 'AEMET', items: [{ level: 'amarillo' }, { level: 'rojo' }] };
    render(<AlertBanner alerts={{ ...quiet, weather_warnings: weather }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('2 avisos de AEMET vigentes (nivel máximo: rojo)');
    expect(screen.getByRole('alert').className).toContain('bg-red-700');
  });

  it('si no hay avisos de AEMET descargados lo dice', () => {
    render(<AlertBanner alerts={{ ...quiet, weather_warnings: { status: 'SIN_DATOS', source: 'AEMET', items: [] } }} />);
    expect(screen.getByText(/Avisos de AEMET: sin datos/)).toBeInTheDocument();
  });

  it('si falla la conexión dice SIN DATOS', () => {
    render(<AlertBanner alerts={null} error />);
    expect(screen.getByRole('alert')).toHaveTextContent('SIN DATOS');
  });
});

describe('LevelBar', () => {
  it('muestra umbrales oficiales y margen libre', () => {
    render(<LevelBar value={1.4} thresholds={TH} unit="m" />);
    expect(screen.getByText(/Margen libre/)).toHaveTextContent('0,6 m hasta el aviso amarillo');
    expect(screen.getByLabelText('Umbral amarillo: 2 m')).toBeInTheDocument();
    expect(screen.getByLabelText('Umbral rojo: 4 m')).toBeInTheDocument();
  });

  it('sin umbrales oficiales dice "umbral no publicado" y no pinta semáforo', () => {
    render(<LevelBar value={1.4} thresholds={null} unit="m" />);
    expect(screen.getByText('umbral no publicado')).toBeInTheDocument();
    expect(screen.queryByLabelText(/Umbral amarillo/)).toBeNull();
  });

  it('por encima del rojo lo dice con palabras', () => {
    render(<LevelBar value={4.3} thresholds={TH} unit="m" />);
    expect(screen.getByText(/Por encima de todos los umbrales oficiales/)).toBeInTheDocument();
  });
});

describe('Freshness', () => {
  it('dato reciente', () => {
    render(<Freshness timestamp="2026-11-11T11:48:00Z" now={NOW} />);
    expect(screen.getByText('hace 12 min')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });
  it('dato obsoleto: aviso visible', () => {
    render(<Freshness timestamp="2026-11-11T09:00:00Z" now={NOW} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Dato antiguo');
    expect(screen.getByRole('alert')).toHaveTextContent('hace 3 h');
  });
});

describe('StationPanel', () => {
  it('explica caudal con equivalencias, lluvia en litros por metro cuadrado y frescura', () => {
    render(<StationPanel station={station()} history={[]} now={NOW} onClose={() => {}} />);
    const panel = screen.getByRole('region', { name: /Río Ejemplo en Ciudad/ });
    expect(panel).toHaveTextContent('125 m³/s');
    expect(panel).toHaveTextContent('125.000 litros por segundo');
    expect(panel).toHaveTextContent('3 piscinas olímpicas por minuto');
    expect(panel).toHaveTextContent('12,5 litros por metro cuadrado');
    expect(panel).toHaveTextContent('hace 12 min');
    expect(within(panel).getByText('Normal')).toBeInTheDocument();
    expect(panel).toHaveTextContent('Qué mide cada sensor');
  });

  it('sin umbral oficial lo dice', () => {
    render(<StationPanel station={station({ status: null, threshold_note: 'umbral no publicado' }, { thresholds: null })} history={[]} now={NOW} onClose={() => {}} />);
    expect(screen.getAllByText(/umbral no publicado/i).length).toBeGreaterThan(0);
  });

  it('dato obsoleto: aviso visible y sin presentar el valor como actual', () => {
    render(<StationPanel station={station({ status: 'DATO_OBSOLETO' }, { timestamp_utc: '2026-11-11T08:00:00Z' })} history={[]} now={NOW} onClose={() => {}} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Dato antiguo');
    expect(screen.getByText(/Última lectura conocida/)).toBeInTheDocument();
  });

  it('sin datos: no enseña valores', () => {
    render(<StationPanel station={station({ status: 'SIN_DATOS', latest: null })} history={[]} now={NOW} onClose={() => {}} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Sin datos');
    expect(screen.queryByText(/m³\/s/)).toBeNull();
  });

  it('embalse: porcentaje y si guarda o suelta agua', () => {
    const s = station({}, { flow_m3s: null, level_m: null, rain_1h_mm: null, thresholds: null, reservoir_pct: 71, reservoir_hm3: 142 });
    const history = [{ timestamp_utc: '2026-11-11T11:48:00Z', reservoir_hm3: 142 }, { timestamp_utc: '2026-11-11T09:48:00Z', reservoir_hm3: 140.6 }];
    render(<StationPanel station={s} history={history} now={NOW} onClose={() => {}} />);
    expect(screen.getByText(/71 % lleno/)).toBeInTheDocument();
    expect(screen.getByText(/Está guardando agua/)).toBeInTheDocument();
  });

  it('en modo demo lleva la etiqueta grande', () => {
    render(<StationPanel station={station()} history={[]} now={NOW} demo onClose={() => {}} />);
    expect(screen.getByText('DATOS DE DEMOSTRACIÓN')).toBeInTheDocument();
  });
});

describe('avisos permanentes', () => {
  it('aviso legal', () => {
    render(<LegalBar />);
    expect(screen.getByRole('contentinfo')).toHaveTextContent('Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil.');
  });
  it('etiqueta de demostración', () => {
    render(<DemoBadge />);
    expect(screen.getByText('DATOS DE DEMOSTRACIÓN')).toBeInTheDocument();
  });
});
