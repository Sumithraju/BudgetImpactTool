import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `@types/node` is not a dependency of this project and adding one for a
// single environment read would be a poor trade, so the one global actually
// needed is declared here instead.
declare const process: { env: Record<string, string | undefined> };

// 5173 is the documented default (run.sh, STATUS.md section 1.3). It is a
// default rather than a requirement: the API is proxied below, so the browser
// only ever sees one origin and the dev server's own port is not load-bearing
// for CORS, callbacks or anything else. A harness that assigns a port via the
// environment therefore just works.
const DEFAULT_PORT = 5173;
const port = Number(process.env.PORT) || DEFAULT_PORT;

export default defineConfig({
  plugins: [react()],
  server: {
    port,
    proxy: {
      "/api": { target: "http://localhost:8077", changeOrigin: true },
      "/health": { target: "http://localhost:8077", changeOrigin: true },
    },
  },
});
