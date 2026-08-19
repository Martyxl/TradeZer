"use client";

import Link from "next/link";

// Sdílený nocturne rám pro auth stránky (login/registrace).
export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4" style={{ background: "radial-gradient(1000px 600px at 80% -160px, #2b2741bf, transparent 60%), #161826" }}>
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-lg font-medium text-[#e9e9ed]">
          <svg width="18" height="18" viewBox="0 0 18 18"><path d="M1 13 L6 7 L9 10 L13 4 L17 4" fill="none" stroke="#9184d9" strokeWidth="1.6" strokeLinecap="square" /><circle cx="13" cy="4" r="2" fill="#9184d9" /></svg>
          tradezer
        </Link>
        <div className="rounded-2xl border border-[#3f424d] bg-[#232532] p-6">
          <h1 className="text-xl font-medium text-[#e9e9ed]">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-gray-400">{subtitle}</p>}
          <div className="mt-5">{children}</div>
        </div>
      </div>
      <style>{`
        .tz-input { width:100%; min-height:38px; padding:6px 12px; font-size:14px; color:#e9e9ed; background:#161826; border:1px solid rgba(233,233,237,0.16); border-radius:8px; outline:none; }
        .tz-input:focus { border-color:#9184d9; }
        .tz-btn-primary { margin-top:4px; min-height:38px; border-radius:8px; font-size:14px; font-weight:500; color:#161826; background:#9184d9; border:none; cursor:pointer; }
        .tz-btn-primary:hover { background:#a7a1db; }
        .tz-btn-primary:disabled { opacity:.55; cursor:not-allowed; }
      `}</style>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-gray-400">{label}</span>
      {children}
    </label>
  );
}
