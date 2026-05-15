import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/interview': 'http://localhost:8000',
      '/voice': 'http://localhost:8000',
    },
  },
})
