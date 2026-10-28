import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  async redirects() {
    return [
      { source: "/admn", destination: "/admin", permanent: false },
      ...["product", "investigate", "examples", "runs", "results", "run"].map((route) => ({ source: `/${route}`, destination: `/app/${route}`, permanent: false })),
    ];
  },
};
export default nextConfig;
