import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const api = "http://127.0.0.1:8765"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { proxy: Object.fromEntries(["/stream", "/control", "/state", "/render", "/camera", "/take"].map((p) => [p, api])) },
  build: { outDir: "../src/jev_drive/web/dist", emptyOutDir: true, chunkSizeWarningLimit: 2000 },
})
