import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CameraView from '../components/CameraView.jsx';

vi.mock('../api.js', () => ({ api: { camera: vi.fn() } }));
import { api } from '../api.js';

const NOW = new Date('2026-11-12T08:00:00Z');
const camera = (status = {}, extra = {}) => ({
  camera: {
    id: '112', image_url: 'https://etraffic.dgt.es/camarasEtraffic/112.jpg', origin_url: 'https://infocar.dgt.es/etraffic/',
    distance_km: 0.8, focus_verified: true, refresh_seconds: 120,
    status: { status: 'OK', message: null, last_modified_utc: '2026-11-12T07:56:00Z', age_minutes: 4, ...status }, ...extra,
  },
});

async function mount(response) {
  api.camera.mockResolvedValue(response);
  render(<CameraView stationId="t:1" now={NOW} />);
  await act(async () => {});
}

beforeEach(() => { api.camera.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

describe('CameraView (solo ver, sin análisis)', () => {
  it('sin cámara verificada cerca no enseña ninguna imagen', async () => {
    await mount({ camera: null, reason: 'No hay ninguna cámara verificada a menos de 3 km.' });
    expect(screen.getByText(/No hay ninguna cámara verificada/)).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('con señal: imagen enlazada directamente, antigüedad y enlace al origen', async () => {
    await mount(camera());
    const img = screen.getByRole('img', { name: /cámara de tráfico/i });
    expect(img.getAttribute('src')).toMatch(/^https:\/\/etraffic\.dgt\.es\/camarasEtraffic\/112\.jpg\?_=/);
    expect(img).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(screen.getByText(/actualizada hace 4 min/i)).toBeInTheDocument();
    expect(screen.getByText(/a 0,8 km/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /ver en el origen/i });
    expect(link).toHaveAttribute('href', 'https://infocar.dgt.es/etraffic/');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('imagen antigua: "Cámara sin señal" y NINGUNA imagen', async () => {
    await mount(camera({ status: 'SIN_SENAL', message: 'Cámara sin señal: la última imagen tiene 180 min', age_minutes: 180 }));
    expect(screen.getByRole('alert')).toHaveTextContent('Cámara sin señal');
    expect(screen.queryByRole('img', { name: /cámara de tráfico/i })).toBeNull();
  });

  it('si la imagen no carga pasa a "Cámara sin señal"', async () => {
    await mount(camera());
    await act(async () => { screen.getByRole('img', { name: /cámara de tráfico/i }).dispatchEvent(new Event('error')); });
    expect(screen.getByRole('alert')).toHaveTextContent('Cámara sin señal');
    expect(screen.queryByRole('img', { name: /cámara de tráfico/i })).toBeNull();
  });

  it('si la API falla: sin señal, nunca la última imagen', async () => {
    api.camera.mockRejectedValue(new Error('HTTP 500'));
    render(<CameraView stationId="t:1" now={NOW} />);
    await act(async () => {});
    expect(screen.getByRole('alert')).toHaveTextContent('Cámara sin señal');
  });

  it('no pinta la imagen hasta saber que está al día', async () => {
    let resolve;
    api.camera.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<CameraView stationId="t:1" now={NOW} />);
    expect(screen.queryByRole('img')).toBeNull();
    await act(async () => { resolve(camera()); });
    expect(screen.getByRole('img', { name: /cámara de tráfico/i })).toBeInTheDocument();
  });

  it('se refresca sola cada 2 min mientras está abierta y deja de hacerlo al cerrarse', async () => {
    vi.useFakeTimers();
    api.camera.mockResolvedValue(camera());
    const { unmount } = render(<CameraView stationId="t:1" now={NOW} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    const first = screen.getByRole('img', { name: /cámara de tráfico/i }).getAttribute('src');
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(api.camera).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('img', { name: /cámara de tráfico/i }).getAttribute('src')).not.toBe(first);
    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(600_000); });
    expect(api.camera).toHaveBeenCalledTimes(2);
  });
});
