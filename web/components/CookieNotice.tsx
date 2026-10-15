"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const KEY = "tz_notice_ok";

/** Informační lišta o úložišti prohlížeče. Používáme jen nezbytné/funkční úložiště (viz /cookies),
 *  takže souhlas není potřeba — jen informujeme. Pokud někdy přibude analytika, tady přibude volba. */
export function CookieNotice() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try { if (!localStorage.getItem(KEY)) setShow(true); } catch { setShow(true); }
  }, []);

  if (!show) return null;
  const close = () => {
    try { localStorage.setItem(KEY, "1"); } catch { /* ignore */ }
    setShow(false);
  };
  return (
    <div role="region" aria-label="Informace o úložišti prohlížeče"
      className="fixed inset-x-3 bottom-3 z-[60] mx-auto flex max-w-xl flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-white/15 bg-[#0d1216]/95 px-4 py-3 text-xs leading-5 text-white/70 shadow-2xl backdrop-blur">
      <p className="min-w-[220px] flex-1">
        Používáme jen nezbytné úložiště prohlížeče (přihlášení, nastavení). <b className="text-white/90">Žádné sledování ani reklamy.</b>{" "}
        <Link href="/cookies" className="text-[#60ff82] hover:underline">Více</Link>
      </p>
      <button onClick={close}
        className="rounded-md border border-[#60ff82]/40 bg-[#60ff82]/10 px-3 py-1.5 font-medium text-[#8fffab] hover:bg-[#60ff82]/20">
        Rozumím
      </button>
    </div>
  );
}
