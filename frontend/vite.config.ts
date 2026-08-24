import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The API is proxied rather than called cross-origin, so the browser
    // sees one origin and CORS never enters the picture in development.
    proxy: {
      "/api": { target: "http://localhost:8077", changeOrigin: true },
      "/health": { target: "http://localhost:8077", changeOrigin: true },
    },
  },
});
