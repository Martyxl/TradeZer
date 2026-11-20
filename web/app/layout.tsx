import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { CookieNotice } from "@/components/CookieNotice";

const inter = Inter({ subsets: ["latin", "latin-ext"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Tradezer — AI, se kterou se nehádáš",
  description:
    "AI čte zprávy a tržní data v reálném čase, počítá pravděpodobnost dopadu a dává ti směr, trend a doporučení — pro intradenní trading i dlouhodobé investování.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // data-tz-theme/-mode na <html> nastavuje před hydratací skript motivu (lib/theme.ts).
  return (
    <html lang="cs" suppressHydrationWarning>
      <body className={`min-h-screen bg-sunken text-gray-100 antialiased ${inter.variable}`}>
        <AuthProvider>{children}</AuthProvider>
        <CookieNotice />
      </body>
    </html>
  );
}
