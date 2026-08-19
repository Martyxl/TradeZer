"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { AuthShell, Field } from "@/components/AuthShell";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      await login(identifier.trim(), password);
      router.push("/dashboard");
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Přihlášení selhalo");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Přihlásit se" subtitle="E-mailem nebo uživatelským jménem.">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label="E-mail nebo jméno">
          <input type="text" required value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="tvuj@email.cz" className="tz-input" autoComplete="username" />
        </Field>
        <Field label="Heslo">
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="tz-input" autoComplete="current-password" />
        </Field>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <button type="submit" disabled={busy} className="tz-btn-primary">{busy ? "Přihlašuji…" : "Přihlásit se"}</button>
      </form>
      <p className="mt-4 text-sm text-white/60">Nemáš účet? <Link href="/registrace" className="tz-link">Vytvořit účet</Link></p>
    </AuthShell>
  );
}
