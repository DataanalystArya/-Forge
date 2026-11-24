import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FORGE | Autonomous AI-Powered Software Engineering Platform",
  description: "Understand, analyze, debug, modify, test, review and maintain software repositories with multi-agent intelligence.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0A0E17] text-[#F8FAFC] min-h-screen antialiased selection:bg-violet-600/30 selection:text-violet-200">
        {children}
      </body>
    </html>
  );
}
