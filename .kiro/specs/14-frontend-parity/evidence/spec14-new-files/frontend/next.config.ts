import type { NextConfig } from "next";

const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // The app is self-contained in frontend/; do not infer a workspace root from parent lockfiles.
  outputFileTracingRoot: import.meta.dirname,
  turbopack: { root: import.meta.dirname },
  // Spec 14 (OD-148): event files up to 10 MiB pass through the proxy and the Server Action (form overhead included).
  experimental: { serverActions: { bodySizeLimit: "11mb" }, proxyClientMaxBodySize: "11mb" },
};

export default config;
