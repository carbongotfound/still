import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': new URL('./src', import.meta.url).pathname.replace(/^\/(\w:)/, '$1') } },
  base: './',
  build: { outDir: '../still/Shell', emptyOutDir: true },
})
