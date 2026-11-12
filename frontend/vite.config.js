import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// En desarrollo y en "preview", /api se redirige al backend (en Docker lo hace nginx).
const api = {
  '/api': {
    target: process.env.VITE_API_TARGET || 'http://localhost:8000',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
};

export default defineConfig({
  plugins: [react()],
  server: { proxy: api },
  preview: { proxy: api },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/__tests__/setup.js',
    include: ['src/**/*.test.{js,jsx}'],
  },
});
