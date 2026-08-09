import path from "path";
import { defineConfig } from "vitest/config";

// Solo il modulo puro del percorso pratica: nessun ambiente DOM, nessun React.
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
