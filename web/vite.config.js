import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat':   'http://localhost:5003',
      '/reset':  'http://localhost:5003',
      '/health': 'http://localhost:5003',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
