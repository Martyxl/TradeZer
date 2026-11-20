"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Menu, X, History, BarChart3, Sunrise, Target, NotebookPen, Telescope, Landmark, BookOpen, User as UserIcon, LogOut, CreditCard, ShieldCheck, Wallet, Receipt, Waves, Bot, Lock, type LucideIcon } from "lucide-react";
import { SupportButton } from "@/components/SupportButton";
import { ThemePicker, ThemeSwatches } from "@/components/ThemePicker";
import { useAuth } from "@/lib/auth";
import { FREE_ACCESS, hasAccess, planRank, type Tier } from "@/lib/config";

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

function NavLink({ item, active, locked, onNavigate }: { item: NavItem; active: boolean; locked: boolean; onNavigate?: () => void }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-2.5 rounded-xl border px-3 py-2 text-[13.5px] transition-colors ${
        active ? "tz-nav-on font-semibold" : "border-transparent text-gray-400 hover:bg-panel hover:text-white"
      }`}
    >
      <Icon size={16} className="shrink-0" />
      <span className="flex-1 whitespace-nowrap">{item.label}</span>
      {FREE_ACCESS ? (locked && (
        <span className="flex shrink-0 items-center text-gray-500" title="Zdarma po registraci"><Lock size={11} /></span>
      )) : item.tier !== "free" && (
        <span className={`flex shrink-0 items-center gap-0.5 rounded-full border px-1.5 py-px text-[10px] font-semibold ${
          locked ? "border-line text-gray-500" : "border-line-2 text-gray-300"}`}
          title={locked ? `Odemčeno v plánu ${TIER_CHIP[item.tier]}` : `Součást vašeho plánu`}>
          {locked && <Lock size={9} />}{TIER_CHIP[item.tier]}
        </span>
      )}
    </Link>
  );
}

function initials(s: string) {
  return (s || "?").split("@")[0].slice(0, 2).toUpperCase();
}

function UserMenu() {
  const { user, loading, logout } = useAuth();
  if (loading) return <div className="h-9 animate-pulse rounded-xl bg-panel" />;
  if (!user) {
    return (
      <div className="flex flex-col gap-2">
        <Link href="/registrace" className="rounded-full bg-white px-3 py-2 text-center text-sm font-semibold text-on-ink transition-colors hover:bg-white/85">
          Vytvořit účet
        </Link>
        <Link href="/prihlaseni" className="rounded-full border border-line-2 px-3 py-2 text-center text-sm text-gray-300 transition-colors hover:bg-panel hover:text-white">
          Přihlásit
        </Link>
      </div>
    );
  }
  const item = "flex items-center gap-2 rounded-xl px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-panel transition-colors";
  return (
    <div className="flex flex-col gap-0.5">
      {user.is_admin && <Link href="/admin" className={item}><ShieldCheck size={14} /> Admin</Link>}
      <Link href="/ucet" className={item}><UserIcon size={14} /> Účet</Link>
      {!FREE_ACCESS && <Link href="/predplatne" className={item}><CreditCard size={14} /> Předplatné</Link>}
      <button onClick={logout} className={`${item} text-left`}><LogOut size={14} /> Odhlásit</button>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-3 rounded-xl px-2 pb-3 pt-1.5">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-line-2 bg-raised">
        <span className="h-4 w-4 rounded-full bg-gradient-to-br from-mint to-mint-2" />
      </span>
      <span>
        <span className="block font-extrabold leading-tight tracking-tight text-white">Tradezer</span>
        <span className="block text-[11.5px] leading-tight text-gray-500">Dopad zpráv na trh</span>
      </span>
    </Link>
  );
}

function NavTree({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  return (
    <nav aria-label="Hlavní menu" className="flex flex-col gap-0.5">
      {NAV_GROUPS.map((g) => (
        <div key={g.key} className="flex flex-col gap-0.5">
          {g.title && <div className="px-3 pb-1 pt-3.5 text-[11.5px] font-semibold text-gray-500">{g.title}</div>}
          {g.items.map((it) => (
            <NavLink key={it.href} item={it} onNavigate={onNavigate}
              active={pathname.startsWith(it.href)} locked={!hasAccess(user, it.tier)} />
          ))}
        </div>
      ))}
      <div className="mt-3 border-t border-line pt-3">
        <NavLink item={LEGEND} onNavigate={onNavigate} active={pathname.startsWith(LEGEND.href)} locked={false} />
      </div>
    </nav>
  );
}

export function Sidebar() {
  return (
    <aside className="tz-pane tz-side sticky top-5 hidden h-[calc(100vh-2.5rem)] w-[248px] shrink-0 flex-col self-start overflow-hidden rounded-[26px] p-3.5 md:flex">
      <Brand />
      <div className="-mx-1 flex-1 overflow-y-auto px-1 [scrollbar-width:none]">
        <NavTree />
      </div>
      <div className="mt-3 flex flex-col gap-2 border-t border-line pt-3">
        <UserMenu />
        <SupportButton variant="sidebar" />
      </div>
    </aside>
  );
}

const EXTRA_TITLES = [
  { href: "/ucet", label: "Účet" },
  { href: "/predplatne", label: "Předplatné" },
  { href: "/admin", label: "Admin" },
];

/** Název aktuální stránky podle menu (pro horní lištu). */
function usePageTitle(): string {
  const pathname = usePathname();
  const all = [...NAV_GROUPS.flatMap((g) => g.items), LEGEND, ...EXTRA_TITLES];
  return all.find((i) => pathname.startsWith(i.href))?.label ?? "Tradezer";
}

function greeting(d: Date) {
  const h = d.getHours();
  return h < 5 ? "Dobrou noc" : h < 10 ? "Dobré ráno" : h < 18 ? "Dobrý den" : "Dobrý večer";
}

/** Horní pilulková lišta: název stránky, pozdrav podle denní doby, odkaz na účet. */
export function AppTopbar() {
  const { user, loading } = useAuth();
  const title = usePageTitle();
  const [hello, setHello] = useState<string | null>(null);
  useEffect(() => setHello(greeting(new Date())), []);
  return (
    <header className="tz-pane hidden min-h-[54px] items-center gap-3 rounded-full py-1.5 pl-6 pr-1.5 md:flex">
      <div className="min-w-0 flex-1 truncate">
        <span className="font-bold text-white">{title}</span>
        {hello && <span className="ml-3 text-sm text-gray-500">{hello}</span>}
      </div>
      <ThemePicker />
      {!loading && (user ? (
        <Link href="/ucet" className="flex items-center gap-2.5 rounded-full p-0.5 pl-3 hover:bg-panel" title="Účet">
          <span className="hidden text-right lg:block">
            <span className="block max-w-[220px] truncate text-[13px] font-semibold leading-tight text-white">{user.email || user.username}</span>
            <span className="block text-[11.5px] leading-tight text-gray-500">{user.is_admin ? "Admin" : FREE_ACCESS ? "Plný přístup" : user.plan}</span>
          </span>
          <span className="grid h-10 w-10 place-items-center rounded-full border border-line-2 bg-mint-2 text-[12.5px] font-extrabold text-[#fff]">
            {initials(user.email || user.username || "")}
          </span>
        </Link>
      ) : (
        <Link href="/prihlaseni" className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-on-ink hover:bg-white/85">Přihlásit</Link>
      ))}
    </header>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  return (
    <header className="sticky top-3 z-50 mx-3 mt-3 md:hidden">
      <div className="tz-pane tz-blur flex items-center gap-3 rounded-full py-1.5 pl-4 pr-1.5">
        <Link href="/" className="flex items-center gap-2">
          <span className="h-5 w-5 rounded-full bg-gradient-to-br from-mint to-mint-2" />
          <span className="font-extrabold tracking-tight text-white">Tradezer</span>
        </Link>
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={open ? "Zavřít menu" : "Otevřít menu"}
          className="ml-auto grid h-9 w-9 place-items-center rounded-full border border-line bg-raised text-white">
          {open ? <X size={17} /> : <Menu size={17} />}
        </button>
      </div>
      {open && (
        <div className="tz-pane mt-2 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-[22px] p-3" style={{ background: "var(--tz-drawer)" }}>
          <NavTree onNavigate={() => setOpen(false)} />
          <div className="mt-3 border-t border-line pt-3"><ThemeSwatches /></div>
          <div className="mt-3 border-t border-line pt-3"><UserMenu /></div>
        </div>
      )}
    </header>
  );
}
