"use client";

import Link from "next/link";

// Sdílený rám pro auth stránky — Tradezer brand (Neon Candles).
export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4" style={{ background: "radial-gradient(900px 520px at 80% -140px, rgba(96,255,130,0.10), transparent 60%), #060a0c" }}>
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-lg font-medium text-white">
          <svg width="20" height="14" viewBox="0 0 20 14"><path d="M1 12 L7 5 L11 9 L18 1 M18 1 h-5 M18 1 v5" fill="none" stroke="#60ff82" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          tradezer
        </Link>
        <div className="rounded-2xl border border-white/10 bg-[#0a0d0f] p-6">
          <h1 className="text-xl font-medium text-white">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-white/60">{subtitle}</p>}
          <div className="mt-5">{children}</div>
        </div>
      </div>
      <style>{`
        .tz-input { width:100%; min-height:40px; padding:6px 12px; font-size:14px; color:#fff; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.16); border-radius:6px; outline:none; }
        .tz-input:focus { border-color:#60ff82; }
        .tz-btn-primary { margin-top:4px; min-height:42px; border-radius:4px; font-size:15px; font-weight:600; color:#06120a; background:linear-gradient(120deg, oklch(0.74 0.19 148), oklch(0.66 0.18 152)); border:none; cursor:pointer; box-shadow:0 0 24px oklch(0.74 0.19 148 / 0.30); }
        .tz-btn-primary:hover { box-shadow:0 0 36px oklch(0.74 0.19 148 / 0.5); }
        .tz-btn-primary:disabled { opacity:.55; cursor:not-allowed; box-shadow:none; }
        .tz-link { color:#8fffab; }
        .tz-link:hover { text-decoration:underline; }
      `}</style>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-white/60">{label}</span>
      {children}
    </label>
  );
}
