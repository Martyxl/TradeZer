"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { AuthShell, Field } from "@/components/AuthShell";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("email");
    if (q) setEmail(q);
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      await register(email.trim().toLowerCase(), password);
      router.push("/dashboard");
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Registrace selhala");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Vytvořit účet" subtitle="Od první minuty vidíš živé predikce a denní souhrn.">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label="E-mail">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="tvuj@email.cz" className="tz-input" autoComplete="email" />
        </Field>
        <Field label="Heslo (aspoň 6 znaků)">
          <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="tz-input" autoComplete="new-password" />
        </Field>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <button type="submit" disabled={busy} className="tz-btn-primary">{busy ? "Zakládám…" : "Vytvořit účet"}</button>
      </form>
      <p className="mt-4 text-sm text-white/60">Už máš účet? <Link href="/prihlaseni" className="tz-link">Přihlásit se</Link></p>
    </AuthShell>
  );
}
