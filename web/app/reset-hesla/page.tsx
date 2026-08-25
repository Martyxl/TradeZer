"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthShell, Field } from "@/components/AuthShell";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") || "");
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(d?.detail || "Reset selhal");
      setDone(true);
      setTimeout(() => router.push("/prihlaseni"), 1800);
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Reset selhal");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Nové heslo" subtitle={done ? undefined : "Nastav si nové heslo k účtu."}>
      {done ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-white/80">Heslo změněno. Přesměrovávám na přihlášení…</p>
          <Link href="/prihlaseni" className="tz-link text-sm">Přihlásit se</Link>
        </div>
      ) : !token ? (
        <p className="text-sm text-yellow-300">Chybí platný token — použij odkaz z e-mailu.</p>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="Nové heslo (aspoň 6 znaků)">
            <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="tz-input" autoComplete="new-password" />
          </Field>
          {err && <p className="text-sm text-red-400">{err}</p>}
          <button type="submit" disabled={busy} className="tz-btn-primary">{busy ? "Ukládám…" : "Nastavit heslo"}</button>
        </form>
      )}
    </AuthShell>
  );
}
