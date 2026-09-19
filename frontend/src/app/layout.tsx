import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
	title: "AI QA Engine",
	description: "AI-assisted quality assurance workspace for any application team",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
	return <html lang="en"><body>{children}</body></html>;
}
