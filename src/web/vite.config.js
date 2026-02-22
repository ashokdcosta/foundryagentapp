import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/chat': 'http://localhost:9001',
      '/health': 'http://localhost:9001',
      '/config': 'http://localhost:9001'
    }
  }
})
