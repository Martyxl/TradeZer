"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Inbox, Mail, Paperclip, RefreshCw, Reply, Search, Send, X } from "lucide-react";
import { authHeaders, useAuth } from "@/lib/auth";

// Admin pošta info@tradezer.app — přijaté zprávy se stahují z Resendu do DB (trvalý archiv),
// odesílá se přes Resend. HTML e-mailu se zobrazuje jen v izolovaném rámu bez skriptů.

interface Summary {
  id: number; direction: "in" | "out"; from_addr: string; from_name: string | null; to: string[];
  subject: string; snippet: string; date: string; is_read: boolean; has_attachments: boolean;
}
interface Detail extends Summary {
  cc: string[]; text: string | null; html: string | null; message_id: string | null;
  attachments: { id: string; filename: string; size: number | null; content_type: string | null }[];
  thread: Summary[];
}
interface Draft { to: string; cc: string; subject: string; text: string; reply_to_id?: number }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/admin/mail${path}`, {
    ...init, cache: "no-store",
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers || {}) },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || `Chyba ${r.status}`);
  return j as T;
}

const fmtDate = (iso: string) =>
  new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString("cs", { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });

export default function MailPage() {
  const { user, loading } = useAuth();
  const [folder, setFolder] = useState<"in" | "out">("in");
  const [items, setItems] = useState<Summary[]>([]);
  const [unread, setUnread] = useState(0);
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [showHtml, setShowHtml] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await api<{ items: Summary[]; unread: number }>(`?folder=${folder}${q ? `&q=${encodeURIComponent(q)}` : ""}`);
    setItems(r.items); setUnread(r.unread);
  }, [folder, q]);

  const sync = useCallback(async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ added: number }>("/sync", { method: "POST" });
      setMsg(r.added ? `Nových zpráv: ${r.added}` : "Žádná nová pošta");
      await load();
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }, [load]);

  useEffect(() => { if (user?.is_admin) sync(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [user?.is_admin]);
  useEffect(() => { if (user?.is_admin) load().catch(() => {}); }, [folder, user?.is_admin, load]);

  async function open(id: number) {
    setShowHtml(false); setDraft(null);
    const d = await api<Detail>(`/${id}`);
    setDetail(d);
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, is_read: true } : x)));
    if (d.direction === "in") setUnread((u) => Math.max(0, u - (items.find((x) => x.id === id)?.is_read ? 0 : 1)));
  }

  function reply(d: Detail) {
    const quoted = (d.text || "").split("\n").map((l) => `> ${l}`).join("\n");
    setDraft({
      to: d.direction === "in" ? d.from_addr : d.to.join(", "), cc: "",
      subject: /^re:/i.test(d.subject) ? d.subject : `Re: ${d.subject}`,
      text: `\n\n${fmtDate(d.date)} ${d.from_name || d.from_addr} napsal(a):\n${quoted}`, reply_to_id: d.id,
    });
  }

  async function send() {
    if (!draft) return;
    setBusy(true); setMsg(null);
    try {
      await api("/send", { method: "POST", body: JSON.stringify(draft) });
      setMsg("Odesláno"); setDraft(null);
      if (folder === "out") await load();
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }

  async function download(mailId: number, attId: string) {
    try {
      const r = await api<{ url: string }>(`/${mailId}/attachments/${attId}`);
      window.open(r.url, "_blank", "noopener,noreferrer");
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  }

  if (loading) return <div className="h-40 animate-pulse rounded-xl bg-[#1a1d27]" />;
  if (!user?.is_admin) return <p className="text-sm text-gray-400">Jen pro admina.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/admin" className="text-gray-500 hover:text-white" aria-label="Zpět do adminu"><ArrowLeft size={18} /></Link>
        <Mail size={20} className="text-[#60ff82]" />
        <h1 className="text-2xl font-bold text-white">Pošta</h1>
        <span className="text-sm text-gray-500">info@tradezer.app</span>
        <div className="ml-auto flex gap-2">
          <button onClick={sync} disabled={busy}
            className="flex items-center gap-1.5 rounded-lg border border-[#2a2d3a] px-3 py-1.5 text-sm text-gray-300 hover:text-white disabled:opacity-50">
            <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> Načíst novou poštu
          </button>
          <button onClick={() => { setDetail(null); setDraft({ to: "", cc: "", subject: "", text: "" }); }}
            className="flex items-center gap-1.5 rounded-lg bg-[#60ff82] px-3 py-1.5 text-sm font-medium text-[#06120a]">
            <Send size={14} /> Napsat
          </button>
        </div>
      </div>
      {msg && <p className="text-xs text-gray-400">{msg}</p>}

      <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        {/* seznam */}
        <div className="rounded-xl border border-[#2a2d3a] bg-[#151823]">
          <div className="flex items-center gap-1 border-b border-[#2a2d3a] p-2">
            {(["in", "out"] as const).map((f) => (
              <button key={f} onClick={() => { setFolder(f); setDetail(null); }}
                className={`rounded-lg px-3 py-1 text-sm ${folder === f ? "bg-[#1e2536] text-white" : "text-gray-400 hover:text-white"}`}>
                {f === "in" ? <><Inbox size={13} className="mr-1 inline" />Přijaté{unread ? ` (${unread})` : ""}</> : "Odeslané"}
              </button>
            ))}
            <form onSubmit={(e) => { e.preventDefault(); load(); }} className="ml-auto flex items-center gap-1">
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hledat" maxLength={100}
                className="w-28 rounded-md border border-[#2a2d3a] bg-[#1a1d27] px-2 py-1 text-xs text-white placeholder-gray-600" />
              <button type="submit" aria-label="Hledat" className="text-gray-500 hover:text-white"><Search size={14} /></button>
            </form>
          </div>
          <ul className="max-h-[65vh] overflow-y-auto">
            {items.length === 0 && <li className="p-4 text-sm text-gray-500">Žádné zprávy.</li>}
            {items.map((m) => (
              <li key={m.id}>
                <button onClick={() => open(m.id)}
                  className={`w-full border-b border-[#1f2230] px-3 py-2 text-left hover:bg-[#1a1d27] ${detail?.id === m.id ? "bg-[#1a1d27]" : ""}`}>
                  <div className="flex items-center gap-2 text-xs">
                    {!m.is_read && <span className="h-2 w-2 shrink-0 rounded-full bg-[#60ff82]" />}
                    <span className={`truncate ${m.is_read ? "text-gray-400" : "font-semibold text-white"}`}>
                      {m.direction === "in" ? (m.from_name || m.from_addr) : `Komu: ${m.to.join(", ")}`}
                    </span>
                    {m.has_attachments && <Paperclip size={11} className="shrink-0 text-gray-500" />}
                    <span className="ml-auto shrink-0 text-gray-600">{fmtDate(m.date)}</span>
                  </div>
                  <div className={`truncate text-sm ${m.is_read ? "text-gray-300" : "text-white"}`}>{m.subject || "(bez předmětu)"}</div>
                  <div className="truncate text-xs text-gray-600">{m.snippet}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* detail / psaní */}
        <div className="min-h-[300px] rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
          {draft ? (
            <div className="space-y-2">
              <div className="flex items-center">
                <h2 className="text-sm font-semibold text-white">{draft.reply_to_id ? "Odpověď" : "Nová zpráva"}</h2>
                <button onClick={() => setDraft(null)} className="ml-auto text-gray-500 hover:text-white" aria-label="Zavřít"><X size={16} /></button>
              </div>
              {(["to", "cc", "subject"] as const).map((k) => (
                <input key={k} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
                  placeholder={k === "to" ? "Komu (více adres oddělte čárkou)" : k === "cc" ? "Kopie (nepovinné)" : "Předmět"}
                  className="w-full rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-2 text-sm text-white placeholder-gray-600" />
              ))}
              <textarea value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} rows={14}
                className="w-full rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-2 font-mono text-sm text-white" />
              <div className="flex items-center gap-3">
                <button onClick={send} disabled={busy || !draft.to.trim() || !draft.subject.trim() || !draft.text.trim()}
                  className="flex items-center gap-1.5 rounded-lg bg-[#60ff82] px-4 py-2 text-sm font-medium text-[#06120a] disabled:opacity-40">
                  <Send size={14} /> Odeslat
                </button>
                <span className="text-xs text-gray-500">Odešle se z info@tradezer.app</span>
              </div>
            </div>
          ) : detail ? (
            <div className="space-y-3">
              <div>
                <h2 className="text-lg font-semibold text-white">{detail.subject || "(bez předmětu)"}</h2>
                <div className="text-xs text-gray-400">
                  {detail.direction === "in"
                    ? <>Od: <span className="text-gray-200">{detail.from_name ? `${detail.from_name} <${detail.from_addr}>` : detail.from_addr}</span></>
                    : <>Komu: <span className="text-gray-200">{detail.to.join(", ")}</span></>}
                  {detail.cc.length > 0 && <> · Kopie: {detail.cc.join(", ")}</>} · {fmtDate(detail.date)}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => reply(detail)}
                  className="flex items-center gap-1.5 rounded-lg border border-[#2a2d3a] px-3 py-1.5 text-sm text-gray-300 hover:text-white">
                  <Reply size={14} /> Odpovědět
                </button>
                {detail.html && (
                  <button onClick={() => setShowHtml((v) => !v)}
                    className="rounded-lg border border-[#2a2d3a] px-3 py-1.5 text-sm text-gray-400 hover:text-white">
                    {showHtml ? "Zobrazit text" : "Zobrazit HTML"}
                  </button>
                )}
              </div>
              {detail.attachments.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {detail.attachments.map((a) => (
                    <button key={a.id} onClick={() => download(detail.id, a.id)}
                      className="flex items-center gap-1 rounded-md border border-[#2a2d3a] px-2 py-1 text-xs text-blue-300 hover:bg-[#1a1d27]">
                      <Paperclip size={12} /> {a.filename}{a.size ? ` (${Math.ceil(a.size / 1024)} kB)` : ""}
                    </button>
                  ))}
                </div>
              )}
              {showHtml && detail.html ? (
                // sandbox="" = žádné skripty, formuláře ani přístup k Tradezeru; e-mail nemůže nic spustit
                <iframe title="HTML zprávy" sandbox="" srcDoc={detail.html} className="h-[55vh] w-full rounded-lg bg-white" />
              ) : (
                <pre className="max-h-[55vh] overflow-y-auto whitespace-pre-wrap break-words font-sans text-sm text-gray-200">
                  {detail.text || "(zpráva nemá textovou verzi — zobraz HTML)"}
                </pre>
              )}
              {detail.thread.length > 0 && (
                <div className="border-t border-[#2a2d3a] pt-2">
                  <div className="mb-1 text-[11px] uppercase tracking-wider text-gray-500">Ve vlákně</div>
                  {detail.thread.map((t) => (
                    <button key={t.id} onClick={() => open(t.id)} className="block w-full truncate py-0.5 text-left text-xs text-gray-400 hover:text-white">
                      {fmtDate(t.date)} · {t.direction === "in" ? (t.from_name || t.from_addr) : "Ty"} · {t.snippet}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Vyber zprávu vlevo, nebo napiš novou.</p>
          )}
        </div>
      </div>
    </div>
  );
}
