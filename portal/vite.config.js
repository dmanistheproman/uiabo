import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// API calls go to the same origin and Vite forwards /analysis, /account,
// /portal and /admin to the FastAPI backend. The backend needs no CORS
// changes for this.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const proxyTarget = process.env.VITE_PROXY_TARGET || env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000';
  return {
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/analysis': proxyTarget,
      '/account': proxyTarget,
      '/portal': proxyTarget,
      '/admin': proxyTarget,
    },
  },
  };
});
