"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, History, BarChart3, Sunrise, Target, User as UserIcon, LogOut, CreditCard, ShieldCheck } from "lucide-react";
import { SupportButton } from "@/components/SupportButton";
import { useAuth } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/history", label: "Historie", icon: History },
  { href: "/stats", label: "Statistiky", icon: BarChart3 },
  { href: "/orb", label: "ORB Radar", icon: Sunrise },
  { href: "/valuation", label: "Valuation Radar", icon: Target },
];

function PlanBadge({ plan, admin }: { plan: string; admin: boolean }) {
  if (admin) return <span className="rounded bg-[rgba(96,255,130,0.14)] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-[#8fffab]">Admin</span>;
  if (plan === "pro") return <span className="rounded bg-[rgba(96,255,130,0.14)] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-[#8fffab]">Pro</span>;
  return <span className="rounded bg-[#2a2d3a] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-gray-400">Free</span>;
}

function UserMenu() {
  const { user, loading, logout } = useAuth();
  if (loading) return <div className="h-9 animate-pulse rounded-lg bg-[#1a1d27]" />;
  if (!user) {
    return (
      <div className="flex flex-col gap-2">
        <Link href="/prihlaseni" className="rounded-lg border border-[#2a2d3a] px-3 py-2 text-center text-sm text-gray-300 hover:text-white hover:border-gray-500 transition-colors">
          Přihlásit
        </Link>
        <Link href="/registrace" className="rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] px-3 py-2 text-center text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)] transition-colors">
          Vytvořit účet
        </Link>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 px-1 pb-1">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[rgba(96,255,130,0.12)] text-[#8fffab]"><UserIcon size={14} /></div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs text-gray-300">{user.email || user.username}</div>
        </div>
        <PlanBadge plan={user.plan} admin={user.is_admin} />
      </div>
      {user.is_admin && <Link href="/admin" className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm text-[#8fffab] hover:text-white hover:bg-[#1a1d27] transition-colors"><ShieldCheck size={14} /> Admin</Link>}
      <Link href="/ucet" className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-[#1a1d27] transition-colors"><UserIcon size={14} /> Účet</Link>
      <Link href="/predplatne" className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-[#1a1d27] transition-colors"><CreditCard size={14} /> Předplatné</Link>
      <button onClick={logout} className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-left text-sm text-gray-400 hover:text-white hover:bg-[#1a1d27] transition-colors"><LogOut size={14} /> Odhlásit</button>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex flex-col w-56 shrink-0 border-r border-[#2a2d3a] bg-[#12141c] h-screen sticky top-0 self-start overflow-y-auto">
      <Link href="/" className="flex items-center gap-2 px-5 py-5 border-b border-[#2a2d3a]">
        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-green-400 to-blue-500" />
        <div>
          <div className="font-bold text-white tracking-tight leading-tight">Tradezer</div>
          <div className="text-[10px] text-gray-500 leading-tight">News Impact Agent</div>
        </div>
      </Link>

      <nav className="flex flex-col gap-1 p-3">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
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

      <div className="mt-auto flex flex-col gap-3 p-3 border-t border-[#2a2d3a]">
        <UserMenu />
        <SupportButton variant="sidebar" />
      </div>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <header className="md:hidden border-b border-[#2a2d3a] bg-[#0f1117]/80 backdrop-blur sticky top-0 z-50">
      <div className="px-4 py-3 flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-full bg-gradient-to-br from-green-400 to-blue-500" />
          <span className="font-bold text-white tracking-tight">Tradezer</span>
        </Link>
        <nav className="ml-auto flex items-center gap-4 text-sm">
          {NAV_ITEMS.map(({ href, label }) => {
            const active = pathname.startsWith(href);
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
          <Link href={user ? "/ucet" : "/prihlaseni"} className="text-gray-400 hover:text-white">
            <UserIcon size={16} />
          </Link>
        </nav>
      </div>
    </header>
  );
}
