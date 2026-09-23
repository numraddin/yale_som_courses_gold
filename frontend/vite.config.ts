import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind IPv4 explicitly so http://127.0.0.1:5173 works, not just ::1.
    host: '127.0.0.1',
    port: 5173,
  },
})
