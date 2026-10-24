"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { HelpCircle, Send, X } from "lucide-react";
import { authHeaders, useAuth } from "@/lib/auth";

// Chatovací pomocník: vysvětluje, co je na aktuální stránce (pojmy, skóre, karty).
// Odpovídá lokální model na Sparku přes frontu na backendu → web dotazuje stav odpovědi.

interface Msg { role: "user" | "assistant" | "info"; text: string }

// Model občas použije **tučné** — vykresli ho, ať uživatel nevidí hvězdičky.
function renderBold(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={i} className="text-white">{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>);
}

// Text, který uživatel právě vidí (hlavní obsah stránky; otevřený detail/okno první) — pomocník s ním pracuje.
function screenText(): string {
  const main = document.querySelector("main");
  if (!main) return "";
  const dialog = main.querySelector<HTMLElement>('[role="dialog"], .fixed.inset-0');
  const parts = dialog ? ["[OTEVŘENÝ DETAIL]", dialog.innerText, "[STRÁNKA]", main.innerText] : [main.innerText];
  return parts.join("\n").replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim().slice(0, 12000);
}

const POLL_MS = 1500;
const GIVE_UP_MS = 120_000;
const PAGE_HINT: Record<string, string> = {
  discovery: "Co znamená Discovery skóre?",
  valuation: "Jak číst bublinovou mapu?",
  history: "Co je trefa směru a IC?",
  stats: "Co znamená t-stat u živých výsledků?",
  dashboard: "Co je denní bias a trust score?",
  orb: "Co znamená one-sided u ORB?",
};

export function HelpChat() {
  const { user } = useAuth();
  const pathname = usePathname() || "/";
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const page = pathname.split("/")[1] || "dashboard";

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const r = await fetch("/api/help/ask", {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ page: pathname, question: q, context: screenText() }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || "Otázku se nepodařilo odeslat.");
      const t0 = Date.now();
      for (;;) {
        await new Promise((res) => setTimeout(res, POLL_MS));
        const s = await fetch(`/api/help/ask/${j.id}`, { headers: authHeaders(), cache: "no-store" }).then((x) => x.json());
        if (s.status === "done") { setMsgs((m) => [...m, { role: "assistant", text: s.answer }]); break; }
        if (s.status === "error" || s.status === "expired" || Date.now() - t0 > GIVE_UP_MS) {
          throw new Error("Pomocník teď neodpovídá (AI server je možná zaneprázdněný). Zkus to prosím za chvíli, nebo mrkni do Legendy.");
        }
      }
    } catch (e) {
      setMsgs((m) => [...m, { role: "info", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Zavřít pomocníka" : "Otevřít pomocníka"}
        className="fixed bottom-5 right-5 z-40 flex h-12 w-12 items-center justify-center rounded-full border border-[#2f3b55] bg-[#1e2536] text-blue-300 shadow-lg hover:bg-[#26304a]"
      >
        {open ? <X size={20} /> : <HelpCircle size={22} />}
      </button>

      {open && (
        <div className="fixed bottom-20 right-4 left-4 sm:left-auto z-40 flex max-h-[70vh] sm:w-[380px] flex-col rounded-2xl border border-[#2a2d3a] bg-[#11141d] shadow-2xl">
          <div className="border-b border-[#2a2d3a] px-4 py-3">
            <div className="text-sm font-semibold text-white">Pomocník Tradezeru</div>
            <div className="text-[11px] text-gray-500">Vidí text této stránky a vysvětlí, co čísla znamenají a jak je zapojit do rozhodování. Pokyny k nákupu/prodeji nedává.</div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
            {!user && (
              <p className="text-gray-400">Pomocník je pro přihlášené uživatele. <a href="/prihlaseni" className="text-blue-400 underline">Přihlas se</a>.</p>
            )}
            {user && msgs.length === 0 && (
              <div className="text-gray-400">
                <p>Zeptej se, co znamená cokoli na téhle stránce.</p>
                {PAGE_HINT[page] && (
                  <button onClick={() => send(PAGE_HINT[page])}
                    className="mt-2 rounded-lg border border-[#2a2d3a] px-2.5 py-1 text-xs text-blue-300 hover:bg-[#1a1d27]">
                    {PAGE_HINT[page]}
                  </button>
                )}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
                <div className={
                  m.role === "user" ? "max-w-[85%] rounded-xl bg-[#1e2536] px-3 py-2 text-white"
                  : m.role === "assistant" ? "max-w-[95%] whitespace-pre-wrap rounded-xl bg-[#171b27] px-3 py-2 text-gray-200"
                  : "text-xs text-yellow-400"}>
                  {m.role === "assistant" ? renderBold(m.text) : m.text}
                </div>
              </div>
            ))}
            {busy && <div className="text-xs text-gray-500 animate-pulse">Pomocník přemýšlí…</div>}
            <div ref={endRef} />
          </div>

          {user && (
            <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex gap-2 border-t border-[#2a2d3a] p-3">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                maxLength={800}
                placeholder="Na co se chceš zeptat?"
                className="flex-1 rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none"
              />
              <button type="submit" disabled={busy || !input.trim()} aria-label="Odeslat"
                className="rounded-lg bg-blue-600 px-3 text-white disabled:opacity-40">
                <Send size={16} />
              </button>
            </form>
          )}
        </div>
      )}
    </>
  );
}
