import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API requests are proxied to the FastAPI backend in dev, so the frontend
// can use relative /api URLs with no CORS friction.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The native FS watcher drops events on some Windows setups; polling is
    // cheap for a project this size and never misses a write.
    watch: { usePolling: true, interval: 300 },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
