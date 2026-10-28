import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  async redirects() {
    // The demo pages (/examples, /run, /runs, /results, /product, /investigate) stay public; /app/* is the signed-in workspace.
    return [{ source: "/admn", destination: "/admin", permanent: false }];
  },
};
export default nextConfig;
