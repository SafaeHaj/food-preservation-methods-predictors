import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        // Reachable from wherever the dev server runs, which is not always the browser's
        // idea of localhost: in compose the SPA is served from inside a container, where
        // `localhost:8000` is the dev server itself and the gateway is `gateway:8000`.
        // Requests proxied to an unreachable target fail as a 500 from this origin.
        '/api': {
          target: env.VITE_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
