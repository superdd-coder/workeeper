import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"

const API_PORT = process.env.API_PORT || "18900"
const UI_PORT = Number(process.env.UI_PORT) || 5173
const API_TARGET = `http://localhost:${API_PORT}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: UI_PORT,
    proxy: {
      "/api/logs/stream": {
        target: API_TARGET,
        changeOrigin: true,
      },
      "/api": API_TARGET,
      "/health": API_TARGET,
    },
  },
})
