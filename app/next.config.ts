import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Segundo Cérebro runs as `node server.js` behind the Agent Zero gateway (infra/vm/plugins/segundo_cerebro).
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        // Preserve native CSS Module processing; the loader emits global CSS.
        condition: { not: { path: /\.module\.css$/ } },
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
