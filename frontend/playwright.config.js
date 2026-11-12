import { defineConfig, devices } from '@playwright/test';

// Prueba end-to-end contra el backend en modo demostración (sin tocar fuentes reales).
const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass: 'localhost,127.0.0.1' } : undefined;
const API = 'http://localhost:8010';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  reporter: 'list',
  use: { baseURL: 'http://localhost:4173', proxy, trace: 'off' },
  webServer: [
    {
      command: 'cd .. && DEMO_LIVE_FALLBACK=true python3 -m uvicorn backend.main:app --port 8010',
      url: `${API}/stations`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: `VITE_API_TARGET=${API} npm run build && VITE_API_TARGET=${API} npm run preview`,
      url: 'http://localhost:4173',
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
  projects: [
    { name: 'movil', use: { ...devices['Pixel 7'] } },
    { name: 'escritorio', use: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 } },
  ],
});
