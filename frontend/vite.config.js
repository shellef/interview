import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/interview': { target: 'http://localhost:8000', changeOrigin: true },
      '/voice':     { target: 'http://localhost:8000', changeOrigin: true },
      '/practice':  { target: 'http://localhost:8000', changeOrigin: true },
      '/login':     { target: 'http://localhost:8000', changeOrigin: true },
      '/logout':    { target: 'http://localhost:8000', changeOrigin: true },
      '/auth':      { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
