import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "./",   // relative URLs: served by pywebview, the devserver, or file://
  build: {
    // into the Python package, so an installed chisel finds the UI (git-ignored)
    outDir: "../src/chisel/gui/web",
    emptyOutDir: true,
  },
})
