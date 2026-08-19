"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { User as UserIcon, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";

export default function AccountPage() {
  const { user, loading, changePassword } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/prihlaseni");
  }, [loading, user, router]);

  if (loading || !user) {
    return <div className="h-40 animate-pulse rounded-xl bg-[#1a1d27]" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[rgba(96,255,130,0.12)] text-[#8fffab]"><UserIcon size={20} /></div>
        <div>
          <h1 className="text-xl font-semibold text-white">{user.email || user.username}</h1>
          <div className="mt-1 flex items-center gap-2 text-xs">
            <span className="rounded bg-[#2a2d3a] px-2 py-0.5 uppercase text-gray-300">Plán: {user.plan}</span>
            {user.is_admin && <span className="inline-flex items-center gap-1 rounded bg-[rgba(96,255,130,0.14)] px-2 py-0.5 uppercase text-[#8fffab]"><ShieldCheck size={11} /> Admin</span>}
          </div>
        </div>
      </div>

      <ChangePasswordCard onChange={changePassword} />
    </div>
  );
}

function ChangePasswordCard({ onChange }: { onChange: (o: string, n: string) => Promise<void> }) {
  const [oldP, setOldP] = useState("");
  const [newP, setNewP] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null); setBusy(true);
    try {
      await onChange(oldP, newP);
      setMsg({ ok: true, text: "Heslo změněno." });
      setOldP(""); setNewP("");
    } catch (e2) {
      setMsg({ ok: false, text: e2 instanceof Error ? e2.message : "Změna selhala" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-md rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
      <h2 className="text-sm font-semibold text-white">Změna hesla</h2>
      <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs text-gray-400">Staré heslo</span>
          <input type="password" required value={oldP} onChange={(e) => setOldP(e.target.value)} className="acc-input" autoComplete="current-password" />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs text-gray-400">Nové heslo (aspoň 6 znaků)</span>
          <input type="password" required minLength={6} value={newP} onChange={(e) => setNewP(e.target.value)} className="acc-input" autoComplete="new-password" />
        </label>
        {msg && <p className={`text-sm ${msg.ok ? "text-green-400" : "text-red-400"}`}>{msg.text}</p>}
        <button type="submit" disabled={busy} className="mt-1 min-h-9 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)] disabled:opacity-50">{busy ? "Ukládám…" : "Změnit heslo"}</button>
      </form>
      <style>{`.acc-input{min-height:36px;padding:6px 10px;font-size:14px;color:#e5e7eb;background:#0f1117;border:1px solid #2a2d3a;border-radius:8px;outline:none}.acc-input:focus{border-color:#60ff82}`}</style>
    </div>
  );
}
