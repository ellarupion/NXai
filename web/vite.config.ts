import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Прокси /api -> backend в dev-режиме: тот же приём, что nginx делает в проде
    // (см. deploy/nginx/nginx.conf) — фронтенд везде ходит на относительный /api,
    // CORS не возникает вообще.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
    allowedHosts: true,
  },
})
