import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Wochenplan & Einkauf",
        short_name: "Wochenplan",
        description: "Wochenplan bauen, Einkaufsliste erzeugen, nach Bring! pushen",
        lang: "de",
        start_url: "/",
        display: "standalone",
        background_color: "#faf9f7",
        theme_color: "#2f5d50",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Offline nur lesend (ARCHITECTURE.md §7): im Laden ist Bring! die Wahrheit.
        globPatterns: ["**/*.{js,css,html,woff2,png,svg}"],
        navigateFallback: "/index.html",
        runtimeCaching: [
          {
            urlPattern: /\/api\/(weeks|dishes|articles)/,
            handler: "NetworkFirst",
            options: {
              cacheName: "api-read",
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 60, maxAgeSeconds: 60 * 60 * 24 * 7 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/openapi.json": "http://127.0.0.1:8080",
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
