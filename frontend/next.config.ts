import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy /api/* → FastAPI backend (avoids CORS in production)
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: "https://hedge-fund-ai-production.up.railway.app/api/v1/:path*",
      },
    ];
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
      { protocol: "https", hostname: "logo.clearbit.com" },
    ],
  },
  // Required for SSE streaming through Next.js proxy
  experimental: {
    serverActions: { bodySizeLimit: "2mb" },
  },
};

export default nextConfig;
