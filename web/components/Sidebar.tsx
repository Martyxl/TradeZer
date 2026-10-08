"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, History, BarChart3, Sunrise, Target, NotebookPen, Telescope, Landmark, BookOpen, User as UserIcon, LogOut, CreditCard, ShieldCheck, Wallet, Receipt, Waves, Bot, Lock, type LucideIcon } from "lucide-react";
import { SupportButton } from "@/components/SupportButton";
import { useAuth } from "@/lib/auth";
import { planRank, type Tier } from "@/lib/config";

interface NavItem { href: string; label: string; icon: LucideIcon; tier: Tier }
interface NavGroup { key: string; title: string | null; accent: string; items: NavItem[] }

// Menu: Dashboard (univerzální) · Trading · Investice. Uvnitř bloku se položky řadí podle
// tarifu (free → trader → pro → elite), takže to, co je zamčené pod vyšším plánem, je VŽDY níž.
// `sortByTier` je stabilní — v rámci stejného tarifu zůstává pořadí, jak je zapsané.
const GROUPS: NavGroup[] = [
  { key: "home", title: null, accent: "#9ca3af", items: [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, tier: "free" },
  ] },
  { key: "trading", title: "Trading", accent: "#60b4ff", items: [
    { href: "/denik", label: "Deník", icon: NotebookPen, tier: "free" },
    { href: "/history", label: "Historie", icon: History, tier: "free" },
    { href: "/orb", label: "ORB Radar", icon: Sunrise, tier: "free" },
    { href: "/stats", label: "Statistiky", icon: BarChart3, tier: "trader" },
  ] },
  { key: "invest", title: "Investice", accent: "#60ff82", items: [
    { href: "/investice", label: "Investice", icon: Wallet, tier: "free" },
    { href: "/dane", label: "Daně", icon: Receipt, tier: "free" },
    { href: "/fond", label: "TRADEZER investuje", icon: Bot, tier: "free" },
    { href: "/valuation", label: "Valuation Radar", icon: Target, tier: "trader" },
    { href: "/discovery", label: "Discovery", icon: Telescope, tier: "pro" },
    { href: "/smart-money", label: "Smart Money", icon: Landmark, tier: "pro" },
    { href: "/dark-pool", label: "Dark Pool", icon: Waves, tier: "pro" },
  ] },
];
const LEGEND: NavItem = { href: "/legenda", label: "Legenda", icon: BookOpen, tier: "free" };

function sortByTier(items: NavItem[]): NavItem[] {
  return items.map((it, i) => ({ it, i }))
    .sort((a, b) => planRank(a.it.tier) - planRank(b.it.tier) || a.i - b.i)
    .map((x) => x.it);
}
export const NAV_GROUPS: NavGroup[] = GROUPS.map((g) => ({ ...g, items: sortByTier(g.items) }));
const TIER_CHIP: Record<string, string> = { trader: "Trader", pro: "Pro", elite: "Elite" };

function PlanBadge({ plan, admin }: { plan: string; admin: boolean }) {
  if (admin) return <span className="rounded bg-[rgba(96,255,130,0.14)] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-[#8fffab]">Admin</span>;
  const p = (plan || "free").toLowerCase();
  if (p === "free") return <span className="rounded bg-[#2a2d3a] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-gray-400">Free</span>;
  return <span className="rounded bg-[rgba(96,255,130,0.14)] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-[#8fffab]">{p}</span>;
}

function NavLink({ item, accent, active, locked }: { item: NavItem; accent: string; active: boolean; locked: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
        active
          ? "bg-[#1e2536] text-white border border-[#2f3b55]"
          : "text-gray-400 hover:text-white hover:bg-[#1a1d27] border border-transparent"
      }`}
    >
      <Icon size={16} style={active ? { color: accent } : undefined} />
      <span className="flex-1 truncate">{item.label}</span>
      {item.tier !== "free" && (
        <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${
          locked ? "bg-[#1c1f2b] text-gray-500" : "bg-[rgba(96,255,130,0.10)] text-[#8fffab]"}`}
          title={locked ? `Odemčeno v plánu ${TIER_CHIP[item.tier]}` : `Součást vašeho plánu`}>
          {locked && <Lock size={9} />}{TIER_CHIP[item.tier]}
        </span>
      )}
    </Link>
  );
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
  const { user } = useAuth();
  const myRank = user?.is_admin ? 99 : planRank(user?.plan);

  return (
    <aside className="hidden md:flex flex-col w-56 shrink-0 border-r border-[#2a2d3a] bg-[#12141c] h-screen sticky top-0 self-start overflow-y-auto">
      <Link href="/" className="flex items-center gap-2 px-5 py-5 border-b border-[#2a2d3a]">
        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-green-400 to-blue-500" />
        <div>
          <div className="font-bold text-white tracking-tight leading-tight">Tradezer</div>
          <div className="text-[10px] text-gray-500 leading-tight">News Impact Agent</div>
        </div>
      </Link>

      <nav className="flex flex-col gap-3 p-3">
        {NAV_GROUPS.map((g) => (
          <section key={g.key}
            className={g.title ? "rounded-xl border border-[#23263a] bg-[#0f1119] p-1.5" : ""}
            style={g.title ? { borderLeft: `3px solid ${g.accent}` } : undefined}>
            {g.title && (
              <div className="flex items-center gap-1.5 px-2.5 pb-1 pt-1">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: g.accent }} />
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em]" style={{ color: g.accent }}>{g.title}</span>
              </div>
            )}
            <div className="flex flex-col gap-0.5">
              {g.items.map((it) => (
                <NavLink key={it.href} item={it} accent={g.accent}
                  active={pathname.startsWith(it.href)} locked={planRank(it.tier) > myRank} />
              ))}
            </div>
          </section>
        ))}
        <div className="border-t border-[#23263a] pt-2">
          <NavLink item={LEGEND} accent="#9ca3af" active={pathname.startsWith(LEGEND.href)} locked={false} />
        </div>
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
          {[...NAV_GROUPS.map((g) => ({ g, items: g.items })), { g: { key: "legend", accent: "#9ca3af" } as NavGroup, items: [LEGEND] }]
            .map(({ g, items }, gi) => (
            <span key={g.key} className={`flex items-center gap-4 ${gi > 0 ? "border-l border-[#2a2d3a] pl-4" : ""}`}>
              {items.map(({ href, label }) => {
                const active = pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={active ? "text-white" : "text-gray-400 hover:text-white transition-colors"}
                    style={active ? { color: g.accent } : undefined}
                  >
                    {label}
                  </Link>
                );
              })}
            </span>
          ))}
          <Link href={user ? "/ucet" : "/prihlaseni"} className="text-gray-400 hover:text-white">
            <UserIcon size={16} />
          </Link>
        </nav>
      </div>
    </header>
  );
}
