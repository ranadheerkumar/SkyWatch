/** @type {import('next').NextConfig} */
const nextConfig = {
	reactStrictMode: true,
	allowedDevOrigins: ["127.0.0.1", "localhost"],
	async rewrites() {
		return [
			{
				source: "/health",
				destination: "http://127.0.0.1:8000/health",
			},
			{
				source: "/api/:path*",
				destination: "http://127.0.0.1:8000/api/:path*",
			},
		];
	},
};

module.exports = nextConfig;
