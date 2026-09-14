import path from "path";
import { defineConfig } from "vitest/config";

// La suite è per lo più il modulo puro del percorso pratica: nessun ambiente
// DOM. Resta vero anche per i test di components/final-report (slice A del
// report finale): niente DOM — rendono i componenti presentazionali con
// react-dom/server (renderToStaticMarkup), che non lo richiede.
// I test di components/final-report girano nello stesso ambiente node: rendono
// i componenti presentazionali con react-dom/server (renderToStaticMarkup),
// che non richiede DOM.
export default defineConfig({
  // I componenti della slice A del report finale sono JSX senza import di
  // React (runtime automatico, come nel build Next via SWC): anche qui esbuild
  // deve usare il runtime automatico, o «React is not defined».
  esbuild: { jsx: "automatic" },
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts", "components/final-report/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
