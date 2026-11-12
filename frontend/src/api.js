// Cliente de la API del backend. En Docker nginx sirve /api; en desarrollo lo hace el proxy de Vite.
const BASE = import.meta.env.VITE_API_BASE || '/api';

async function get(path) {
  const response = await fetch(`${BASE}${path}`, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`HTTP ${response.status} en ${path}`);
  return response.json();
}

export const api = {
  stations: () => get('/stations'),
  station: (id) => get(`/stations/${encodeURIComponent(id)}`),
  history: (id, limit = 150) => get(`/stations/${encodeURIComponent(id)}/history?limit=${limit}`),
  alerts: () => get('/alerts'),
  propagation: () => get('/propagation'),
};
