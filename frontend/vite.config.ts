import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The board talks to the orchestrator through `/api`, proxied in dev so the
 * browser sees one origin. A proxy rather than CORS on the backend: the API
 * has no business advertising which origins may read a case, and in a real
 * deployment the board is served from the same origin anyway.
 *
 * `/api/cases/{seed}/events` is Server-Sent Events, so the proxy must not
 * buffer it — a buffered stream turns a live case into one delivery at the
 * end, which is exactly the thing the stream exists to avoid.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5178,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        configure: (proxy) => {
          proxy.on("proxyRes", (res) => {
            if ((res.headers["content-type"] ?? "").includes("text/event-stream")) {
              res.headers["cache-control"] = "no-cache, no-transform";
            }
          });
        },
      },
    },
  },
});
