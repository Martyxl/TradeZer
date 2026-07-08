import type { Metadata } from "next";
import "./globals.css";
import { Sidebar, MobileNav } from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Tradezer — News Impact Trading Agent",
  description: "Real-time forex news analysis with AI-powered market impact prediction",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="cs">
      <body className="min-h-screen bg-[#0f1117] text-gray-100 antialiased">
        <MobileNav />
        <div className="flex">
          <Sidebar />
          <main className="flex-1 min-w-0 px-4 py-6 md:px-8">
            <div className="mx-auto max-w-6xl">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
