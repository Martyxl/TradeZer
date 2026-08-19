import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

const inter = Inter({ subsets: ["latin", "latin-ext"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Tradezer — AI, se kterou se nehádáš",
  description:
    "AI čte zprávy a tržní data v reálném čase, počítá pravděpodobnost dopadu a dává ti směr, trend a doporučení — pro intradenní trading i dlouhodobé investování.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="cs">
      <body className={`min-h-screen bg-[#0f1117] text-gray-100 antialiased ${inter.variable}`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
