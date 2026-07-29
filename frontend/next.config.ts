import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";
import path from "path";

const createNextConfig = (phase: string): NextConfig => ({
  // `next dev` and `next build` must not share the same output directory.
  // Running a production build while the local server is active otherwise
  // invalidates its manifests and produces 404s for JS/CSS chunks.
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
  output: "standalone",
  reactStrictMode: true,

  webpack: (config) => {
    // Ensure path aliases work correctly on Netlify
    config.resolve.alias = {
      ...config.resolve.alias,
      '@': path.resolve(__dirname, '.'),
    };
    return config;
  },
});

export default createNextConfig;
