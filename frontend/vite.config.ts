import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_DEV_PROXY_TARGET || "http://localhost:8000";

  return {
    server: {
      host: "::",
      port: 3000,
      hmr: {
        overlay: false,
      },
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          // Note: We do NOT rewrite (strip) the /api prefix here.
          // The Master NGINX Gateway on port 8000 expects the /api prefix to correctly route traffic to the backend.
        },
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
      dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
    },
  };
});
