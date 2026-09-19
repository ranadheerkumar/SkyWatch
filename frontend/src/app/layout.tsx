import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
	title: "SkyWatch | Autonomous QA & Testing Platform",
	description: "Autonomous agentic quality assurance, intelligent test generation, self-healing Playwright execution, and quality intelligence",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
	return <html lang="en"><body>{children}</body></html>;
}
