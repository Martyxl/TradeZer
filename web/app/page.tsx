"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

// ── Tradezer brand — Neon Candles (viz handoff/BRAND.md) ────────────────────
const C = {
  bg: "#060a0c", bgSoft: "#0a0d0f", text: "#ffffff",
  muted: "rgba(255,255,255,0.72)", faint: "rgba(255,255,255,0.65)",
  green: "#60ff82", greenBright: "#7dffa0", greenPale: "#8fffab",
  red: "#ff4040", redBright: "#ff5050",
  border: "rgba(255,255,255,0.22)", surface: "rgba(255,255,255,0.04)",
};
const FONT = "var(--font-inter), 'Inter', system-ui, sans-serif";
const ARROW = "M1 12 L7 5 L11 9 L18 1 M18 1 h-5 M18 1 v5";

// ── Hero: pomalu plující neonové svíčky (přesně dle handoff/design) ─────────
function useNeonCandles(ref: React.RefObject<HTMLCanvasElement | null>, speed = 0.35) {
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const size = () => {
      const r = c.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2);
      c.width = r.width * d; c.height = r.height * d;
    };
    size();
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const rnd = (i: number, s: number) => { const x = Math.sin(i * 127.1 + s * 311.7) * 43758.5453; return x - Math.floor(x); };
    const wave = (x: number) => Math.sin(x * 0.55) * 0.16 + Math.sin(x * 0.21 + 1.7) * 0.22 + Math.sin(x * 1.3) * 0.045;
    const sparks = Array.from({ length: 90 }, (_, i) => ({ x: rnd(i, 1), y: rnd(i, 2), r: 0.6 + rnd(i, 3) * 1.8, ph: rnd(i, 4) * Math.PI * 2, red: rnd(i, 5) > 0.55 }));
    let t = reduce ? 3.4 : 0, raf = 0;
    const frame = () => {
      const d = devicePixelRatio || 1, W = c.width, H = c.height;
      if (!reduce) t += 0.0016 * speed;
      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = "rgba(255,255,255,0.035)"; ctx.lineWidth = 1;
      const g = 64 * d;
      for (let x = 0; x < W; x += g) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
      for (let y = 0; y < H; y += g) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
      for (const s of sparks) {
        const a = 0.1 + (Math.sin(t * 30 + s.ph) + 1) * 0.14;
        ctx.fillStyle = s.red ? `rgba(255,60,60,${a})` : `rgba(60,255,120,${a})`;
        ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.r * d, 0, Math.PI * 2); ctx.fill();
      }
      const cw = 34 * d, gap = 22 * d, step = cw + gap;
      const off = (t * 60 * d) % step, first = Math.floor((t * 60 * d) / step), count = Math.ceil(W / step) + 2;
      ctx.save();
      for (let k = 0; k < count; k++) {
        const i = first + k;
        const x = k * step - off + cw / 2;
        const base = 0.55 + wave(i * 0.5);
        const up = rnd(i, 7) > 0.42 + wave(i * 0.5) * 0.6;
        const bodyH = (26 + rnd(i, 8) * 90) * d;
        const wickH = bodyH + (20 + rnd(i, 9) * 46) * d;
        const y = base * H - bodyH / 2 + (rnd(i, 10) - 0.5) * 40 * d;
        const col = up ? "96,255,130" : "255,64,64";
        const bright = up ? "190,255,205" : "255,170,160";
        ctx.shadowColor = `rgba(${col},0.8)`; ctx.shadowBlur = 26 * d;
        ctx.strokeStyle = `rgba(${col},0.75)`; ctx.lineWidth = 2.4 * d;
        ctx.beginPath(); ctx.moveTo(x, y - (wickH - bodyH) / 2); ctx.lineTo(x, y + bodyH + (wickH - bodyH) / 2); ctx.stroke();
        const grd = ctx.createLinearGradient(x - cw / 2, y, x + cw / 2, y + bodyH);
        grd.addColorStop(0, `rgba(${col},0.95)`); grd.addColorStop(0.5, `rgba(${bright},0.95)`); grd.addColorStop(1, `rgba(${col},0.85)`);
        ctx.fillStyle = grd; ctx.fillRect(x - cw / 2, y, cw, bodyH);
        ctx.shadowBlur = 0;
        ctx.fillStyle = `rgba(${bright},0.5)`;
        ctx.fillRect(x - cw / 2 + 3 * d, y + 3 * d, 5 * d, Math.max(0, bodyH - 6 * d));
      }
      ctx.restore();
      const mas = [
        { hue: "rgba(80,180,255,0.55)", o: 0.06, f: 0.9 },
        { hue: "rgba(255,90,90,0.45)", o: -0.05, f: 1.15 },
        { hue: "rgba(255,210,90,0.4)", o: 0.12, f: 0.7 },
      ];
      for (const m of mas) {
        ctx.strokeStyle = m.hue; ctx.lineWidth = 1.6 * d;
        ctx.beginPath();
        for (let px = 0; px <= 100; px++) {
          const u = px / 100;
          const wi = (u * W + t * 60 * d) / step;
          const yy = (0.55 + wave(wi * 0.5 * m.f) * 0.9 + m.o + Math.sin(u * 4 + t * 8) * 0.015) * H;
          px ? ctx.lineTo(u * W, yy) : ctx.moveTo(u * W, yy);
        }
        ctx.stroke();
      }
      if (!reduce) raf = requestAnimationFrame(frame);
    };
    frame();
    const onResize = () => { size(); if (reduce) frame(); };
    addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", onResize); };
  }, [ref, speed]);
}

// ── „Jak myslím" — signálové pole konvergující k cenové linii (zeleně) ──────
function useSignalField(ref: React.RefObject<HTMLCanvasElement | null>) {
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const size = () => { const r = c.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2); c.width = r.width * d; c.height = r.height * d; };
    size();
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const N = 90;
    const pts = Array.from({ length: N }, (_, i) => ({ u: i / (N - 1), phase: Math.random() * Math.PI * 2, amp: 8 + Math.random() * 26, jitter: (Math.random() - 0.5) * 0.5 }));
    let t = reduce ? 2 : 0, raf = 0;
    const acc = (a: number) => `rgba(96,255,130,${a})`;
    const wave = (u: number, tt: number) => Math.sin(u * 5.2 + tt * 0.7) * 0.22 + Math.sin(u * 11.7 - tt * 1.1) * 0.1 + Math.sin(u * 2.1 + tt * 0.3) * 0.3;
    const frame = () => {
      const d = devicePixelRatio || 1, W = c.width, H = c.height;
      if (!reduce) t += 0.012;
      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = "rgba(96,255,130,0.07)"; ctx.lineWidth = 1;
      for (let gy = 1; gy < 5; gy++) { ctx.beginPath(); ctx.moveTo(0, (H * gy) / 5); ctx.lineTo(W, (H * gy) / 5); ctx.stroke(); }
      ctx.strokeStyle = acc(0.5); ctx.lineWidth = 1.4 * d;
      ctx.beginPath();
      for (let i = 0; i <= 100; i++) { const u = i / 100, y = H * (0.5 + wave(u, t) * 0.4); i ? ctx.lineTo(u * W, y) : ctx.moveTo(u * W, y); }
      ctx.stroke();
      for (const p of pts) {
        const baseY = H * (0.5 + wave(p.u, t) * 0.4);
        const y = baseY + Math.sin(t * 2 + p.phase) * p.amp * d;
        const x = (p.u + p.jitter * 0.01) * W;
        const near = 1 - Math.min(1, Math.abs(y - baseY) / (30 * d));
        ctx.fillStyle = acc(0.25 + near * 0.6);
        ctx.beginPath(); ctx.arc(x, y, (1 + near * 1.6) * d, 0, Math.PI * 2); ctx.fill();
      }
      const ly = H * (0.5 + wave(1, t) * 0.4);
      ctx.fillStyle = acc(0.9); ctx.beginPath(); ctx.arc(W - 4 * d, ly, 3.5 * d, 0, Math.PI * 2); ctx.fill();
      if (!reduce) raf = requestAnimationFrame(frame);
    };
    frame();
    const onResize = () => { size(); if (reduce) frame(); };
    addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", onResize); };
  }, [ref]);
}

function Stat({ big, label }: { big: string; label: string }) {
  return (
    <div>
      <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: "clamp(36px,3.6vw,52px)", lineHeight: 1.05, color: C.text, margin: 0, fontFeatureSettings: "'tnum' 1" }}>{big}</p>
      <p style={{ fontSize: 13, letterSpacing: "0.06em", textTransform: "uppercase", color: "rgba(255,255,255,0.6)", margin: "12px 0 0" }}>{label}</p>
    </div>
  );
}

function Feature({ n, title, body, first }: { n: string; title: string; body: string; first?: boolean }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(48px,120px) minmax(0,420px) minmax(0,1fr)", gap: "20px clamp(24px,4vw,72px)", alignItems: "baseline", padding: "42px 0", borderTop: first ? "none" : "1px solid rgba(255,255,255,0.09)" }} className="tz-feat">
      <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 15, color: C.green, margin: 0, fontFeatureSettings: "'tnum' 1" }}>{n}</p>
      <h2 style={{ fontFamily: FONT, fontWeight: 500, fontSize: 24, lineHeight: "28px", letterSpacing: "-0.01em", margin: 0, color: C.text }}>{title}</h2>
      <p style={{ fontSize: 15.5, lineHeight: "28px", margin: 0, color: "rgba(255,255,255,0.78)", maxWidth: "52ch" }}>{body}</p>
    </div>
  );
}

export default function Landing() {
  const heroCanvas = useRef<HTMLCanvasElement>(null);
  const demoCanvas = useRef<HTMLCanvasElement>(null);
  useNeonCandles(heroCanvas);
  useSignalField(demoCanvas);
  const router = useRouter();
  const [email, setEmail] = useState("");
  const goRegister = () => router.push(email ? `/registrace?email=${encodeURIComponent(email)}` : "/registrace");

  const primaryCta = { fontFamily: FONT, fontSize: 15, fontWeight: 600, padding: "13px 28px", borderRadius: 4, cursor: "pointer", border: "none", background: "linear-gradient(120deg, oklch(0.74 0.19 148), oklch(0.66 0.18 152))", color: "#06120a", boxShadow: "0 0 28px oklch(0.74 0.19 148 / 0.35)" } as const;
  const ghostCta = { fontFamily: FONT, fontSize: 15, padding: "13px 28px", borderRadius: 4, cursor: "pointer", background: C.surface, border: `1px solid ${C.border}`, color: C.text, textDecoration: "none" } as const;

  return (
    <div style={{ fontFamily: FONT, color: C.text, background: C.bg, minHeight: "100vh" }}>
      {/* Nav */}
      <nav style={{ display: "flex", alignItems: "center", gap: 22, padding: "16px clamp(20px,5vw,72px)", maxWidth: 1200, margin: "0 auto", position: "relative", zIndex: 3 }}>
        <span style={{ fontFamily: FONT, fontWeight: 500, fontSize: 18, marginRight: "auto", display: "inline-flex", alignItems: "center", gap: 10 }}>
          <svg width="20" height="14" viewBox="0 0 20 14"><path d={ARROW} fill="none" stroke={C.green} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          tradezer
        </span>
        <a href="#funkce" style={{ color: C.text, textDecoration: "none", fontSize: 14 }} className="tz-navlink">Co umím</a>
        <a href="#ukazka" style={{ color: C.text, textDecoration: "none", fontSize: 14 }} className="tz-navlink">Ukázka</a>
        <a href="#pristup" style={{ color: C.text, textDecoration: "none", fontSize: 14 }} className="tz-navlink">Přístup</a>
        <Link href="/prihlaseni" style={{ color: C.muted, textDecoration: "none", fontSize: 14 }} className="tz-navlink">Přihlásit</Link>
        <button type="button" onClick={goRegister} style={primaryCta}>Získat výhodu</button>
      </nav>

      {/* Hero — centrovaný, canvas svíčky + gradient */}
      <section style={{ position: "relative", overflow: "hidden", minHeight: "88vh", display: "grid", alignItems: "center", marginTop: -70 }}>
        <canvas ref={heroCanvas} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(1000px 600px at 50% 48%, rgba(6,8,10,0.97) 30%, rgba(6,8,10,0.7) 60%, transparent 80%)" }} />
        <div style={{ position: "relative", maxWidth: 1100, margin: "0 auto", padding: "96px clamp(20px,5vw,72px)", textAlign: "center" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 10, fontSize: 13, letterSpacing: "0.2em", textTransform: "uppercase", color: C.faint }}>
            <svg width="20" height="14" viewBox="0 0 20 14"><path d={ARROW} fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            tradezer
          </span>
          <h1 style={{ fontFamily: FONT, fontWeight: 500, fontSize: "clamp(46px,6.4vw,92px)", lineHeight: 1.05, letterSpacing: "-0.02em", margin: "24px 0 0", color: C.text, textShadow: "0 0 44px rgba(0,0,0,0.9)" }}>
            Se mnou&nbsp;<span style={{ color: C.redBright, textShadow: "rgba(255,80,80,0.45) 0 0 30px" }}>nehádáš</span>.<br />
            Se mnou máš <span style={{ color: C.greenBright, textShadow: "rgba(125,255,160,0.5) 0 0 30px" }}>náskok</span>.
          </h1>
          <p style={{ fontSize: 17, lineHeight: "28px", maxWidth: "54ch", margin: "24px auto 0", color: C.muted }}>
            AI, která čte zprávy a tržní data dřív než trh. Směr, trend a pravděpodobnost dopadu — pro trading i dlouhodobé investice.
          </p>
          <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap", marginTop: 32 }}>
            <button type="button" onClick={goRegister} style={primaryCta}>Vytvořit účet</button>
            <a href="#ukazka" style={ghostCta}>Jak myslím</a>
          </div>
        </div>
      </section>

      {/* Signální karta */}
      <section style={{ maxWidth: 460, margin: "0 auto", padding: "0 clamp(20px,5vw,72px) 24px", position: "relative", zIndex: 2 }}>
        <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, padding: 20, backdropFilter: "blur(6px)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <span style={{ fontFamily: FONT, fontWeight: 500, fontSize: 15 }}>EUR / USD</span>
              <span style={{ fontSize: 12, letterSpacing: "0.06em", textTransform: "uppercase", color: C.faint }}>Spot</span>
            </div>
            <span style={{ fontSize: 15, color: C.green, fontFeatureSettings: "'tnum' 1" }}>1,0842 ▲</span>
          </div>
          <svg viewBox="0 0 320 130" style={{ display: "block", width: "100%", marginTop: 16 }}>
            <line x1="0" y1="46" x2="320" y2="46" stroke="rgba(255,255,255,0.08)" /><line x1="0" y1="92" x2="320" y2="92" stroke="rgba(255,255,255,0.08)" />
            <g strokeWidth="1">
              {[[14,30,86,42,34,"sell"],[40,50,100,58,30,"sell"],[66,60,110,70,28,"buy"],[92,46,96,54,30,"buy"],[118,52,98,60,26,"sell"],[144,36,88,44,32,"buy"],[170,24,72,32,28,"buy"],[196,30,76,38,24,"sell"],[222,18,66,26,30,"buy"]].map((k, i) => {
                const [x, y1, y2, ry, rh, side] = k as [number, number, number, number, number, string];
                const ink = side === "buy" ? C.green : C.red;
                return <g key={i}><line x1={x} y1={y1} x2={x} y2={y2} stroke={ink} /><rect x={x - 5} y={ry} width="10" height={rh} fill={ink} opacity="0.85" /></g>;
              })}
            </g>
            <path d="M232 32 C 258 18, 280 26, 318 10" fill="none" stroke={C.green} strokeWidth="1.6" strokeDasharray="5 4" />
            <circle cx="232" cy="32" r="3" fill={C.green} />
          </svg>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginTop: 16, padding: 12, border: `1px solid rgba(96,255,130,0.35)`, borderRadius: 4, background: "rgba(96,255,130,0.06)" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: C.green, marginTop: 5, flex: "none", boxShadow: "0 0 10px rgba(96,255,130,0.6)" }} />
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: "20px", color: C.text }}>
              <span style={{ color: C.greenPale }}>tradezer:</span> ECB jestřábí tón — tenhle typ zprávy historicky +0,3 % do 4 h. Směr ↑, pravděpodobnost 78 %.
            </p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 16 }}>
            <button type="button" style={{ fontFamily: FONT, fontSize: 14, letterSpacing: "0.04em", padding: "9px 0", borderRadius: 4, cursor: "pointer", background: "transparent", border: `1px solid ${C.green}`, color: C.green }}>BUY · LONG</button>
            <button type="button" style={{ fontFamily: FONT, fontSize: 14, letterSpacing: "0.04em", padding: "9px 0", borderRadius: 4, cursor: "pointer", background: "transparent", border: `1px solid ${C.red}`, color: C.red }}>SELL · SHORT</button>
          </div>
        </div>
      </section>

      {/* Statistiky */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "70px clamp(20px,5vw,72px)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,auto)", justifyContent: "space-between", gap: "42px 28px" }} className="tz-stats">
          <Stat big="5 min" label="Od zprávy k predikci" />
          <Stat big="5" label="Placených datových zdrojů" />
          <Stat big="24/7" label="Nikdy nespím" />
          <Stat big="1" label="Výhoda, kterou ostatní nemají" />
        </div>
      </section>

      {/* Co se mnou získáš */}
      <section id="funkce" style={{ maxWidth: 1200, margin: "0 auto", padding: "28px clamp(20px,5vw,72px) 60px" }}>
        <span style={{ display: "block", fontSize: 13, letterSpacing: "0.06em", textTransform: "uppercase", color: C.green, marginBottom: 14 }}>Co se mnou získáš</span>
        <Feature first n="01" title="Zprávy čtu dřív než trh" body="Makro kalendář, zpravodajské feedy i tržní data z placených zdrojů stahuju každých pár minut a každou zprávu okamžitě klasifikuju. Zatímco ostatní čtou, co se stalo, ty už víš, co to pravděpodobně udělá s cenou." />
        <Feature n="02" title="Pravděpodobnosti, ne názory" body="Každá zpráva dostane pravděpodobnost směru — nahoru, dolů, neutrál — zkombinovanou s tím, jak trh na stejný typ zpráv reagoval historicky. Žádné „možná“. Když si nejsem jistý, uvidíš to v čísle." />
        <Feature n="03" title="Přesnost si ověříš sám" body="Každá predikce zůstává v historii vedle toho, co trh skutečně udělal. Denní souhrn pro tradery, dlouhodobé trendy a valuace pro investory — a moje úspěšnost černá na bílém, za 90 dní zpětně." />
      </section>

      {/* Jak myslím */}
      <section id="ukazka" style={{ maxWidth: 1200, margin: "0 auto", padding: "40px clamp(20px,5vw,72px) 88px", display: "grid", gridTemplateColumns: "minmax(0,5fr) minmax(0,7fr)", gap: "28px clamp(24px,5vw,96px)", alignItems: "center" }} className="tz-demo">
        <div>
          <span style={{ display: "block", fontSize: 13, letterSpacing: "0.06em", textTransform: "uppercase", color: C.green, marginBottom: 14 }}>Jak myslím</span>
          <h2 style={{ fontFamily: FONT, fontWeight: 500, fontSize: 32, lineHeight: "42px", letterSpacing: "-0.012em", margin: 0, color: C.text }}>Nehádám. Počítám.</h2>
          <p style={{ fontSize: 15.5, lineHeight: "28px", color: "rgba(255,255,255,0.78)", margin: "28px 0 0", maxWidth: "48ch" }}>Každý bod v poli je zpráva nebo datový signál. AI klasifikaci vážím historickou reakcí trhu na stejný typ událostí — čím víc dat, tím víc rozhoduje statistika. Tohle není magie, je to kalibrovaná pravděpodobnost.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 28 }}>
            {["zprávy", "historické korelace", "kalibrace", "sentiment"].map((t, i) => (
              <span key={t} style={{ fontSize: 11, letterSpacing: "0.02em", padding: "3px 10px", borderRadius: 6, background: i === 0 ? "rgba(96,255,130,0.14)" : "rgba(255,255,255,0.06)", color: i === 0 ? C.greenPale : "rgba(255,255,255,0.7)" }}>{t}</span>
            ))}
          </div>
        </div>
        <div style={{ position: "relative", minHeight: 340, border: "1px solid rgba(255,255,255,0.09)", borderRadius: 8, overflow: "hidden", background: C.bgSoft }}>
          <canvas ref={demoCanvas} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
          <div style={{ position: "absolute", left: 16, bottom: 14, display: "flex", alignItems: "center", gap: 8, fontSize: 12, letterSpacing: "0.06em", textTransform: "uppercase", color: C.faint }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: C.green, boxShadow: "0 0 8px rgba(96,255,130,0.7)" }} /> Živé signálové pole
          </div>
        </div>
      </section>

      {/* Citace */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "0 clamp(20px,5vw,72px) 88px" }}>
        <blockquote style={{ fontFamily: FONT, fontWeight: 500, fontSize: "clamp(24px,2.6vw,34px)", lineHeight: "42px", maxWidth: "32ch", margin: 0, color: C.text }}>„Dřív jsem měl otevřených osm záložek a stejně jsem byl poslední, kdo to viděl. Teď mám otevřenou jednu.“</blockquote>
        <p style={{ fontSize: 15.5, color: "rgba(255,255,255,0.6)", margin: "28px 0 0" }}>— trader z uzavřené bety</p>
      </section>

      {/* Přístup / registrace */}
      <section id="pristup" style={{ maxWidth: 1200, margin: "0 auto", padding: "70px clamp(20px,5vw,72px) 56px", borderTop: "1px solid rgba(255,255,255,0.09)" }}>
        <h3 style={{ fontFamily: FONT, fontWeight: 500, fontSize: 24, margin: 0, color: C.text }}>Trh nečeká. Ty už nemusíš.</h3>
        <p style={{ fontSize: 15.5, lineHeight: "28px", color: "rgba(255,255,255,0.78)", margin: "24px 0 0", maxWidth: "58ch" }}>Vytvoř si účet a od první minuty vidíš živé predikce, denní souhrn i moji úspěšnost. Feed platím já — ty jen sbíráš náskok.</p>
        <form onSubmit={(e) => { e.preventDefault(); goRegister(); }} style={{ display: "flex", gap: 10, alignItems: "stretch", maxWidth: 480, marginTop: 24 }}>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="tvuj@email.cz" aria-label="E-mail"
            style={{ flex: 1, minHeight: 46, padding: "6px 14px", fontSize: 15, color: C.text, background: C.surface, border: `1px solid rgba(255,255,255,0.16)`, borderRadius: 4, outline: "none" }} />
          <button type="submit" style={primaryCta}>Vytvořit účet</button>
        </form>
      </section>

      <footer style={{ maxWidth: 1200, margin: "0 auto", padding: "56px clamp(20px,5vw,72px)", fontSize: 13, lineHeight: "28px", color: "rgba(255,255,255,0.5)" }}>
        tradezer.app — AI, se kterou se nehádáš. Obchodování nese riziko; výhoda ho jen zmenšuje.
      </footer>

      <style>{`
        .tz-navlink:hover { color: ${C.green} !important; }
        @media (max-width: 900px) {
          .tz-demo { grid-template-columns: 1fr !important; }
          .tz-stats { grid-template-columns: 1fr 1fr !important; }
          .tz-feat { grid-template-columns: 1fr !important; gap: 8px !important; }
        }
      `}</style>
    </div>
  );
}
