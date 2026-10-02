import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "./",   // relative URLs: served by pywebview, the devserver, or file://
  build: {
    // into the Python package, so an installed lorewrite finds the UI (git-ignored)
    outDir: "../src/lorewrite/gui/web",
    emptyOutDir: true,
  },
})
