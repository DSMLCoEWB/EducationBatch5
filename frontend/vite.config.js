const react = require("@vitejs/plugin-react");
const path = require("path");
const { defineConfig } = require("vite");

module.exports = defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
  },
  build: {
    outDir: 'build'
  }
});
