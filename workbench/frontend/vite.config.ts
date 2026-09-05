import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  build: { outDir: '../static', emptyOutDir: true, assetsInlineLimit: 0 },
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8080' } },
})
