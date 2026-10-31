import type { NextConfig } from "next";

const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // The app is self-contained in frontend/; do not infer a workspace root from parent lockfiles.
  outputFileTracingRoot: import.meta.dirname,
  turbopack: { root: import.meta.dirname },
  allowedDevOrigins: [
    "localhost:3000",
    "127.0.0.1:3000",
    "192.168.0.101:3000",
    "192.168.0.101",
  ],
  // Spec 14 (OD-148): event files up to 10 MiB pass through the proxy and the Server Action (form overhead included).
  experimental: {
    serverActions: {
      bodySizeLimit: "11mb",
      allowedOrigins: [
        "localhost:3000",
        "127.0.0.1:3000",
        "192.168.0.101:3000",
        "192.168.0.101",
        "*.local:3000",
      ],
    },
    proxyClientMaxBodySize: "11mb",
  },
};

export default config;
