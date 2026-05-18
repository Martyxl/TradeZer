import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tradezer — News Impact Trading Agent",
  description: "Real-time forex news analysis with AI-powered market impact prediction",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="cs">
      <body className="min-h-screen bg-[#0f1117] text-gray-100 antialiased">
        <header className="border-b border-[#2a2d3a] bg-[#0f1117]/80 backdrop-blur sticky top-0 z-50">
          <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 rounded-full bg-gradient-to-br from-green-400 to-blue-500" />
              <span className="font-bold text-white text-lg tracking-tight">Tradezer</span>
            </div>
            <span className="text-gray-600 text-sm">News Impact Trading Agent</span>
            <nav className="ml-auto flex gap-4 text-sm text-gray-400">
              <a href="/" className="hover:text-white transition-colors">Dashboard</a>
              <a href="/history" className="hover:text-white transition-colors">Historie</a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
