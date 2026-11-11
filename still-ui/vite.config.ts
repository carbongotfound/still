import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// still/Shell/source.txt: a hash of every file in still-ui but node_modules and dist (each ./path, a newline, then its
// bytes without CR). mac/build.sh works it out the same way and stops when the bundle was built from an older still-ui.
const ui = fileURLToPath(new URL('.', import.meta.url))
function sourceHash() {
  const files: string[] = []
  const walk = (dir: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (e.name === 'node_modules' || e.name === 'dist') continue
      const p = join(dir, e.name)
      if (e.isDirectory()) walk(p)
      else if (e.isFile()) files.push('./' + relative(ui, p).split(sep).join('/'))
    }
  }
  walk(ui)
  files.sort((a, b) => Buffer.compare(Buffer.from(a), Buffer.from(b)))
  const hash = createHash('sha256')
  for (const f of files) hash.update(f + '\n').update(readFileSync(join(ui, f)).filter(byte => byte !== 13))
  return hash.digest('hex')
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), { name: 'source-hash', generateBundle() { this.emitFile({ type: 'asset', fileName: 'source.txt', source: sourceHash() + '\n' }) } }],
  resolve: { alias: { '@': new URL('./src', import.meta.url).pathname.replace(/^\/(\w:)/, '$1') } },
  base: './',
  build: { outDir: '../still/Shell', emptyOutDir: true },
})
