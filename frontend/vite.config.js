import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies /api and /frame.jpg to the always-on Python
// backend (see ../src/hongtai_screen_app/control_server.py) so the
// dev server and the backend can run on different ports without
// hitting CORS -- the backend itself sets no CORS headers on purpose
// (see control_server.py's docstring: it only ever expects same-origin
// callers). `npm run build`'s output (dist/) is served directly BY
// that same backend in production (control_server.py's do_GET falls
// back to frontend/dist for any path that isn't an API route), so
// production has no cross-origin request to make in the first place.
const BACKEND = "http://127.0.0.1:8899";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": BACKEND,
      "/frame.jpg": BACKEND,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
