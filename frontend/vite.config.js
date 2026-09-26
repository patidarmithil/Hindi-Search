import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on uvicorn; 127.0.0.1 (not "localhost") avoids a
// ~2 s IPv6 fallback delay on Windows.
const API_TARGET = process.env.API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: true } },
  },
});
