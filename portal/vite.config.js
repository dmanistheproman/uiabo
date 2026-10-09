import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// API calls go to the same origin and Vite forwards /analysis, /account and
// /portal to the FastAPI backend. The backend needs no CORS changes for this.
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/analysis': proxyTarget,
      '/account': proxyTarget,
      '/portal': proxyTarget,
    },
  },
});
