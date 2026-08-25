"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthShell, Field } from "@/components/AuthShell";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await fetch("/api/auth/request-reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
    } catch {
      /* generická odpověď — nezáleží */
    } finally {
      setBusy(false);
      setDone(true);
    }
  };

  return (
    <AuthShell title="Zapomenuté heslo" subtitle={done ? undefined : "Zadej email, který jsi použil při registraci."}>
      {done ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-white/80">
            Pokud účet s tímto emailem existuje, poslali jsme ti e-mail s odkazem pro nastavení nového hesla
            (platí 1 hodinu). Zkontroluj i složku Spam.
          </p>
          <Link href="/prihlaseni" className="tz-link text-sm">Zpět na přihlášení</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="E-mail">
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="tvuj@email.cz" className="tz-input" autoComplete="email" />
          </Field>
          <button type="submit" disabled={busy} className="tz-btn-primary">{busy ? "Odesílám…" : "Požádat o reset"}</button>
          <Link href="/prihlaseni" className="tz-link text-sm">Zpět na přihlášení</Link>
        </form>
      )}
    </AuthShell>
  );
}
