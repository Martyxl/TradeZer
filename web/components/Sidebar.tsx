"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, History, BarChart3 } from "lucide-react";
import { SupportButton } from "@/components/SupportButton";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/history", label: "Historie", icon: History },
  { href: "/stats", label: "Statistiky", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex flex-col w-56 shrink-0 border-r border-[#2a2d3a] bg-[#12141c] min-h-screen sticky top-0">
      <div className="flex items-center gap-2 px-5 py-5 border-b border-[#2a2d3a]">
        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-green-400 to-blue-500" />
        <div>
          <div className="font-bold text-white tracking-tight leading-tight">Tradezer</div>
          <div className="text-[10px] text-gray-500 leading-tight">News Impact Agent</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1 p-3">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "bg-[#1e2536] text-white border border-[#2f3b55]"
                  : "text-gray-400 hover:text-white hover:bg-[#1a1d27] border border-transparent"
              }`}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto p-3 border-t border-[#2a2d3a]">
        <SupportButton variant="sidebar" />
      </div>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname();

  return (
    <header className="md:hidden border-b border-[#2a2d3a] bg-[#0f1117]/80 backdrop-blur sticky top-0 z-50">
      <div className="px-4 py-3 flex items-center gap-3">
        <div className="h-6 w-6 rounded-full bg-gradient-to-br from-green-400 to-blue-500" />
        <span className="font-bold text-white tracking-tight">Tradezer</span>
        <nav className="ml-auto flex gap-4 text-sm">
          {NAV_ITEMS.map(({ href, label }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={active ? "text-white" : "text-gray-400 hover:text-white transition-colors"}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
