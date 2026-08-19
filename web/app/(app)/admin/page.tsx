"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, Users, LogIn, Eye, CreditCard, type LucideIcon } from "lucide-react";
import { useAuth, authToken } from "@/lib/auth";

interface Row {
  id: number; email: string | null; username: string | null; plan: string;
  is_admin: boolean; login_count: number; created_at: string | null; last_login: string | null;
}
interface Overview {
  stats: { total_users: number; pro: number; free: number; admins: number; logins_total: number; reg_7d: number; reg_30d: number; visits: number };
  users: Row[];
  payments: unknown[];
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user || !user.is_admin) { router.replace("/dashboard"); return; }
    fetch("/api/auth/admin/overview", { headers: { Authorization: `Bearer ${authToken()}` }, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Načtení selhalo"))))
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [loading, user, router]);

  if (loading || (!data && !err)) return <div className="h-40 animate-pulse rounded-xl bg-[#1a1d27]" />;
  if (!user?.is_admin) return null;
  if (err) return <p className="text-sm text-red-400">{err}</p>;
  const s = data!.stats;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <ShieldCheck size={20} className="text-[#60ff82]" />
        <h1 className="text-2xl font-bold text-white">Admin</h1>
      </div>

      {/* Statistiky */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={Users} label="Registrace" value={s.total_users} sub={`+${s.reg_7d} za 7 dní · +${s.reg_30d} za 30`} />
        <StatCard icon={CreditCard} label="Plány" value={`${s.pro} Pro`} sub={`${s.free} Free`} />
        <StatCard icon={LogIn} label="Přihlášení" value={s.logins_total} sub="celkem" />
        <StatCard icon={Eye} label="Návštěvnost" value={s.visits} sub="celkem" />
      </div>

      {/* Platby */}
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
        <h2 className="text-sm font-semibold text-white">Platby</h2>
        <p className="mt-2 text-sm text-gray-500">
          Platby zatím nejsou spuštěné live. Až se napojí (Stripe), objeví se tu jednotlivé transakce a předplatná.
        </p>
      </div>

      {/* Uživatelé */}
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2a2d3a]">
          <h2 className="text-sm font-semibold text-white">Uživatelé</h2>
          <span className="text-xs text-gray-500">{data!.users.length} zobrazeno</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase text-gray-500 border-b border-[#2a2d3a]">
                <th className="text-left px-4 py-2 font-medium">Účet</th>
                <th className="text-left px-3 py-2 font-medium">Plán</th>
                <th className="text-left px-3 py-2 font-medium">Registrace</th>
                <th className="text-left px-3 py-2 font-medium">Poslední přihlášení</th>
                <th className="text-right px-4 py-2 font-medium">Loginů</th>
              </tr>
            </thead>
            <tbody>
              {data!.users.map((u) => (
                <tr key={u.id} className="border-b border-[#1e222e] hover:bg-[#1a1d27]">
                  <td className="px-4 py-2 text-gray-200">
                    {u.email || u.username || "—"}
                    {u.is_admin && <span className="ml-2 rounded bg-[rgba(96,255,130,0.14)] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-[#8fffab]">Admin</span>}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${u.plan === "pro" ? "bg-[rgba(96,255,130,0.14)] text-[#8fffab]" : "bg-[#2a2d3a] text-gray-400"}`}>{u.plan}</span>
                  </td>
                  <td className="px-3 py-2 text-gray-400">{u.created_at?.replace("T", " ") ?? "—"}</td>
                  <td className="px-3 py-2 text-gray-400">{u.last_login?.replace("T", " ") ?? "—"}</td>
                  <td className="px-4 py-2 text-right text-gray-300">{u.login_count}</td>
                </tr>
              ))}
              {data!.users.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">Zatím žádné registrace.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub }: { icon: LucideIcon; label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="flex items-center gap-2 text-xs text-gray-500"><Icon size={14} className="text-[#60ff82]" /> {label}</div>
      <div className="mt-2 text-2xl font-bold text-white">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-gray-500">{sub}</div>}
    </div>
  );
}
