"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, Users, LogIn, Eye, CreditCard, KeyRound, Trash2, ArrowUpDown, type LucideIcon } from "lucide-react";
import { useAuth, authToken } from "@/lib/auth";

interface Row {
  id: number; email: string | null; username: string | null; plan: string;
  is_admin: boolean; login_count: number; reset_requested: boolean;
  created_at: string | null; last_login: string | null;
}
interface Overview {
  stats: { total_users: number; pro: number; free: number; admins: number; logins_total: number; reg_7d: number; reg_30d: number; visits: number; reset_requests: number };
  users: Row[];
  reg_by_day: { date: string; count: number }[];
}

async function adminPost(path: string, method = "POST", body?: unknown) {
  const res = await fetch(`/api/auth/admin/${path}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken()}` },
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(d?.detail || "Akce selhala");
  return d;
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [resetResult, setResetResult] = useState<{ user: string; temp: string } | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    fetch("/api/auth/admin/overview", { headers: { Authorization: `Bearer ${authToken()}` }, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Načtení selhalo"))))
      .then(setData).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user || !user.is_admin) { router.replace("/dashboard"); return; }
    load();
  }, [loading, user, router, load]);

  const resetPw = async (u: Row) => {
    setBusyId(u.id);
    try {
      const d = await adminPost(`users/${u.id}/reset-password`);
      setResetResult({ user: d.user, temp: d.temp_password });
      load();
    } catch (e) { setErr(e instanceof Error ? e.message : "Reset selhal"); } finally { setBusyId(null); }
  };
  const togglePlan = async (u: Row) => {
    setBusyId(u.id);
    try { await adminPost(`users/${u.id}/plan`, "POST", { plan: u.plan === "pro" ? "free" : "pro" }); load(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Změna selhala"); } finally { setBusyId(null); }
  };
  const delUser = async (u: Row) => {
    if (!confirm(`Smazat účet ${u.email || u.username}? Nevratné.`)) return;
    setBusyId(u.id);
    try { await adminPost(`users/${u.id}`, "DELETE"); load(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Smazání selhalo"); } finally { setBusyId(null); }
  };

  if (loading || (!data && !err)) return <div className="h-40 animate-pulse rounded-xl bg-[#1a1d27]" />;
  if (!user?.is_admin) return null;
  if (err && !data) return <p className="text-sm text-red-400">{err}</p>;
  const s = data!.stats;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <ShieldCheck size={20} className="text-[#60ff82]" />
        <h1 className="text-2xl font-bold text-white">Admin</h1>
      </div>

      {resetResult && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-[rgba(96,255,130,0.35)] bg-[rgba(96,255,130,0.08)] px-4 py-3 text-sm">
          <span className="text-white">Nové dočasné heslo pro <strong>{resetResult.user}</strong>:</span>
          <code className="rounded bg-black/40 px-2 py-0.5 font-mono text-[#8fffab]">{resetResult.temp}</code>
          <span className="text-xs text-gray-400">Předej ho uživateli — v Účtu si ho změní.</span>
          <button onClick={() => setResetResult(null)} className="ml-auto text-xs text-gray-500 hover:text-white">zavřít</button>
        </div>
      )}
      {err && data && <p className="text-sm text-red-400">{err}</p>}

      {/* Statistiky */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={Users} label="Registrace" value={s.total_users} sub={`+${s.reg_7d} za 7 dní · +${s.reg_30d} za 30`} />
        <StatCard icon={CreditCard} label="Plány" value={`${s.pro} Pro`} sub={`${s.free} Free`} />
        <StatCard icon={LogIn} label="Přihlášení" value={s.logins_total} sub="celkem" />
        <StatCard icon={Eye} label="Návštěvnost" value={s.visits} sub="celkem" />
      </div>

      {/* Graf registrací */}
      <RegChart data={data!.reg_by_day} />

      {/* Žádosti o reset */}
      {s.reset_requests > 0 && (
        <div className="rounded-xl border border-yellow-800 bg-yellow-950/30 px-4 py-3 text-sm text-yellow-300">
          <KeyRound size={14} className="mr-1 inline" /> {s.reset_requests} žádost(í) o reset hesla — dole u uživatele klikni na „Reset".
        </div>
      )}

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
                <th className="text-right px-3 py-2 font-medium">Loginů</th>
                <th className="text-right px-4 py-2 font-medium">Akce</th>
              </tr>
            </thead>
            <tbody>
              {data!.users.map((u) => (
                <tr key={u.id} className="border-b border-[#1e222e] hover:bg-[#1a1d27]">
                  <td className="px-4 py-2 text-gray-200">
                    {u.email || u.username || "—"}
                    {u.is_admin && <span className="ml-2 rounded bg-[rgba(96,255,130,0.14)] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-[#8fffab]">Admin</span>}
                    {u.reset_requested && <span className="ml-2 rounded bg-yellow-900/50 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-yellow-300">Reset?</span>}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${u.plan === "pro" ? "bg-[rgba(96,255,130,0.14)] text-[#8fffab]" : "bg-[#2a2d3a] text-gray-400"}`}>{u.plan}</span>
                  </td>
                  <td className="px-3 py-2 text-gray-400">{u.created_at?.replace("T", " ") ?? "—"}</td>
                  <td className="px-3 py-2 text-gray-400">{u.last_login?.replace("T", " ") ?? "—"}</td>
                  <td className="px-3 py-2 text-right text-gray-300">{u.login_count}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center justify-end gap-1.5">
                      <ActionBtn title="Reset hesla" onClick={() => resetPw(u)} disabled={busyId === u.id}><KeyRound size={13} /></ActionBtn>
                      <ActionBtn title={u.plan === "pro" ? "Přepnout na Free" : "Přepnout na Pro"} onClick={() => togglePlan(u)} disabled={busyId === u.id}><ArrowUpDown size={13} /></ActionBtn>
                      <ActionBtn title="Smazat účet" onClick={() => delUser(u)} disabled={busyId === u.id || u.id === user.id} danger><Trash2 size={13} /></ActionBtn>
                    </div>
                  </td>
                </tr>
              ))}
              {data!.users.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-sm text-gray-500">Zatím žádné registrace.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Platby */}
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
        <h2 className="text-sm font-semibold text-white">Platby</h2>
        <p className="mt-2 text-sm text-gray-500">Platby zatím nejsou spuštěné live. Až se napojí (Stripe), objeví se tu transakce a předplatná.</p>
      </div>
    </div>
  );
}

function ActionBtn({ children, title, onClick, disabled, danger }: { children: React.ReactNode; title: string; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button title={title} onClick={onClick} disabled={disabled}
      className={`flex h-7 w-7 items-center justify-center rounded-md border transition-colors disabled:opacity-40 ${danger ? "border-[#3a2020] text-red-400 hover:bg-red-950/40" : "border-[#2a2d3a] text-gray-400 hover:text-white hover:bg-[#1e2230]"}`}>
      {children}
    </button>
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

function RegChart({ data }: { data: { date: string; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const total = data.reduce((a, d) => a + d.count, 0);
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-white">Registrace za 30 dní</h2>
        <span className="text-xs text-gray-500">{total} celkem</span>
      </div>
      <div className="mt-4 flex h-24 items-end gap-[3px]">
        {data.map((d) => (
          <div key={d.date} title={`${d.date}: ${d.count}`} className="flex-1 rounded-sm bg-[rgba(96,255,130,0.35)] hover:bg-[#60ff82]"
            style={{ height: `${Math.max(3, (d.count / max) * 100)}%` }} />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-gray-600">
        <span>{data[0]?.date.slice(5)}</span>
        <span>{data[data.length - 1]?.date.slice(5)}</span>
      </div>
    </div>
  );
}
