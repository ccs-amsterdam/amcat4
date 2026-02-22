/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export (meaning we only use client components!)
  output: 'export',
  images: {
    unoptimized: true,
  },

  // In local evelopment (with 'next dev' we proxy the backend to fake samesite
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:5000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
