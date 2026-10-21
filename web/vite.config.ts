/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Development only: forward API calls to a locally running backend.
    proxy: { '/api': { target: process.env.VITE_BACKEND ?? 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 700 },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
