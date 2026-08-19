"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

// ── Nocturne paleta (design system z Claude Design) ─────────────────────────
const C = {
  bg: "#161826", surface: "#232532", text: "#e9e9ed", accent: "#9184d9",
  accent300: "#d2cefd", accent900: "#2b2741", n300: "#cfd3e5", n700: "#595d6c",
  n800: "#3f424d", n900: "#292b31", section: "#262a60", sectionGlow: "#353b80",
  buy: "oklch(0.75 0.11 158)", sell: "oklch(0.66 0.14 22)",
};
const FONT = "var(--font-inter), 'Inter', system-ui, sans-serif";

// ── Hero particle field ─────────────────────────────────────────────────────
function useParticles(ref: React.RefObject<HTMLCanvasElement | null>, density = 90) {
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const size = () => {
      const r = c.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2);
      c.width = r.width * d; c.height = r.height * d;
    };
    size();
    let pts: { x: number; y: number; vx: number; vy: number; r: number }[] = [];
    const seed = () => {
      const n = Math.round(density * (c.width / (1600 * (devicePixelRatio || 1))) + density * 0.4);
      pts = Array.from({ length: n }, () => ({
        x: Math.random() * c.width, y: Math.random() * c.height,
        vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.25,
        r: 0.8 + Math.random() * 1.6,
      }));
    };
    seed();
    let lastW = c.width, raf = 0;
    const acc = (a: number) => `rgba(145,132,217,${a})`;
    const tick = () => {
      if (c.width !== lastW) { lastW = c.width; seed(); }
      const d = devicePixelRatio || 1;
      ctx.clearRect(0, 0, c.width, c.height);
      const link = 110 * d;
      for (const p of pts) {
        p.x += p.vx * d; p.y += p.vy * d;
        if (p.x < 0 || p.x > c.width) p.vx *= -1;
        if (p.y < 0 || p.y > c.height) p.vy *= -1;
      }
      ctx.lineWidth = 1;
      for (let i = 0; i < pts.length; i++)
        for (let j = i + 1; j < pts.length; j++) {
          const a = pts[i], b = pts[j], dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (dist < link) {
            ctx.strokeStyle = acc((1 - dist / link) * 0.16);
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      for (const p of pts) {
        ctx.fillStyle = acc(0.55);
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r * d, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const onResize = () => size();
    addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", onResize); };
  }, [ref, density]);
}

// ── Demo „signálové pole" ───────────────────────────────────────────────────
function useSignalField(ref: React.RefObject<HTMLCanvasElement | null>) {
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const size = () => {
      const r = c.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2);
      c.width = r.width * d; c.height = r.height * d;
    };
    size();
    const N = 90;
    const pts = Array.from({ length: N }, (_, i) => ({
      u: i / (N - 1), phase: Math.random() * Math.PI * 2,
      amp: 8 + Math.random() * 26, jitter: (Math.random() - 0.5) * 0.5,
    }));
    let t = 0, raf = 0;
    const acc = (a: number) => `rgba(145,132,217,${a})`;
    const wave = (u: number, tt: number) =>
      Math.sin(u * 5.2 + tt * 0.7) * 0.22 + Math.sin(u * 11.7 - tt * 1.1) * 0.1 + Math.sin(u * 2.1 + tt * 0.3) * 0.3;
    const tick = () => {
      const d = devicePixelRatio || 1, W = c.width, H = c.height;
      t += 0.012;
      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = "rgba(145,132,217,0.07)"; ctx.lineWidth = 1;
      for (let gy = 1; gy < 5; gy++) { ctx.beginPath(); ctx.moveTo(0, (H * gy) / 5); ctx.lineTo(W, (H * gy) / 5); ctx.stroke(); }
      ctx.strokeStyle = acc(0.5); ctx.lineWidth = 1.4 * d;
      ctx.beginPath();
      for (let i = 0; i <= 100; i++) {
        const u = i / 100, y = H * (0.5 + wave(u, t) * 0.4);
        i ? ctx.lineTo(u * W, y) : ctx.moveTo(u * W, y);
      }
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
      ctx.fillStyle = acc(0.9);
      ctx.beginPath(); ctx.arc(W - 4 * d, ly, 3.5 * d, 0, Math.PI * 2); ctx.fill();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const onResize = () => size();
    addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", onResize); };
  }, [ref]);
}

function Stat({ big, label }: { big: string; label: string }) {
  return (
    <div>
      <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: "clamp(36px,3.6vw,52px)", lineHeight: "56px", color: C.text, margin: 0, fontFeatureSettings: "'tnum' 1" }}>{big}</p>
      <p style={{ fontSize: 13, letterSpacing: "0.06em", textTransform: "uppercase", color: "rgba(233,233,237,0.64)", margin: "12px 0 0" }}>{label}</p>
    </div>
  );
}

function Feature({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(48px,120px) minmax(0,420px) minmax(0,1fr)", gap: "20px clamp(24px,4vw,72px)", alignItems: "baseline", padding: "34px 0", borderTop: `1px solid ${C.n800}` }}>
      <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 15, color: C.accent, margin: 0 }}>{n}</p>
      <h2 style={{ fontFamily: FONT, fontWeight: 500, fontSize: 24, lineHeight: "28px", margin: 0, color: C.text }}>{title}</h2>
      <p style={{ fontSize: 15.5, lineHeight: "28px", margin: 0, color: "rgba(233,233,237,0.78)", maxWidth: "52ch" }}>{body}</p>
    </div>
  );
}

export default function Landing() {
  const heroCanvas = useRef<HTMLCanvasElement>(null);
  const demoCanvas = useRef<HTMLCanvasElement>(null);
  useParticles(heroCanvas);
  useSignalField(demoCanvas);
  const router = useRouter();
  const [email, setEmail] = useState("");

  const goRegister = () => router.push(email ? `/registrace?email=${encodeURIComponent(email)}` : "/registrace");
  const btn = { fontFamily: FONT, fontWeight: 500, fontSize: 14, padding: "8px 14px", borderRadius: 8, cursor: "pointer", background: "transparent" } as const;

  return (
    <div style={{ fontFamily: FONT, color: C.text, background: `radial-gradient(1200px 720px at 82% -160px, ${C.accent900}bf, transparent 60%), radial-gradient(1100px 800px at -10% 100%, rgba(0,0,0,0.3), transparent 55%), ${C.bg}`, minHeight: "100vh" }}>
      {/* Nav */}
      <nav style={{ display: "flex", alignItems: "center", gap: 20, padding: "14px clamp(20px,5vw,72px)", maxWidth: 1344, margin: "0 auto" }}>
        <span style={{ fontFamily: FONT, fontWeight: 500, fontSize: 18, marginRight: "auto", display: "inline-flex", alignItems: "center", gap: 10 }}>
          <svg width="18" height="18" viewBox="0 0 18 18"><path d="M1 13 L6 7 L9 10 L13 4 L17 4" fill="none" stroke={C.accent} strokeWidth="1.6" strokeLinecap="square" /><circle cx="13" cy="4" r="2" fill={C.accent} /></svg>
          tradezer
        </span>
        <a href="#funkce" style={{ color: C.text, textDecoration: "none", fontSize: 14 }}>Co umím</a>
        <a href="#ukazka" style={{ color: C.text, textDecoration: "none", fontSize: 14 }}>Ukázka</a>
        <Link href="/prihlaseni" style={{ color: C.text, textDecoration: "none", fontSize: 14 }}>Přihlásit</Link>
        <button type="button" onClick={goRegister} style={{ ...btn, color: C.accent, border: `1px solid ${C.accent}` }}>Získat výhodu</button>
      </nav>

      {/* Hero */}
      <section style={{ position: "relative", overflow: "hidden" }}>
        <canvas ref={heroCanvas} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} />
        <div style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "96px clamp(20px,5vw,72px) 72px", display: "grid", gridTemplateColumns: "minmax(0,7fr) minmax(300px,5fr)", gap: "48px clamp(32px,5vw,88px)", alignItems: "center" }} className="tz-hero-grid">
          <div>
            <h1 style={{ fontFamily: FONT, fontWeight: 500, fontSize: "clamp(42px,5.6vw,78px)", lineHeight: 1.11, letterSpacing: "-0.015em", margin: 0, color: C.text }}>
              <span style={{ display: "block" }}>Se mnou nehádáš.</span>
              <span style={{ display: "block", color: C.accent }}>Se mnou máš náskok.</span>
            </h1>
            <p style={{ fontSize: 17, lineHeight: "28px", maxWidth: "54ch", margin: "28px 0 0", color: C.text }}>
              Tradezer čte zprávy a tržní data v reálném čase, počítá pravděpodobnost dopadu a dává ti směr, trend a doporučení — pro intradenní trading i dlouhodobé investování. Feed platím já. Výhodu máš ty.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 28 }}>
              <button type="button" onClick={goRegister} style={{ ...btn, color: C.accent, border: `1px solid ${C.accent}` }}>Vytvořit účet</button>
              <a href="#ukazka" style={{ ...btn, color: C.accent, textDecoration: "none" }}>Podívat se, jak myslím</a>
            </div>
          </div>
          {/* Ticket karta */}
          <div style={{ background: "rgba(41,43,49,0.72)", border: `1px solid ${C.n700}`, borderRadius: 8, boxShadow: "0 16px 40px rgba(0,0,0,0.65)", padding: 20, backdropFilter: "blur(6px)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span style={{ fontFamily: FONT, fontWeight: 500, fontSize: 15, color: C.text }}>EUR / USD</span>
                <span style={{ fontSize: 12, letterSpacing: "0.06em", textTransform: "uppercase", color: C.n300 }}>Spot</span>
              </div>
              <span style={{ fontSize: 15, color: C.buy }}>1,0842 ▲</span>
            </div>
            <svg viewBox="0 0 320 130" style={{ display: "block", width: "100%", marginTop: 16 }}>
              <line x1="0" y1="46" x2="320" y2="46" stroke={C.n800} /><line x1="0" y1="92" x2="320" y2="92" stroke={C.n800} />
              <g strokeWidth="1">
                {[[14,30,86,42,34,"sell"],[40,50,100,58,30,"sell"],[66,60,110,70,28,"buy"],[92,46,96,54,30,"buy"],[118,52,98,60,26,"sell"],[144,36,88,44,32,"buy"],[170,24,72,32,28,"buy"],[196,30,76,38,24,"sell"],[222,18,66,26,30,"buy"]].map((k, i) => {
                  const [x, y1, y2, ry, rh, side] = k as [number,number,number,number,number,string];
                  const ink = side === "buy" ? C.buy : C.sell;
                  return <g key={i}><line x1={x} y1={y1} x2={x} y2={y2} stroke={ink} /><rect x={x - 5} y={ry} width="10" height={rh} fill={ink} opacity="0.85" /></g>;
                })}
              </g>
              <path d="M232 32 C 258 18, 280 26, 318 10" fill="none" stroke={C.accent} strokeWidth="1.6" strokeDasharray="5 4" />
              <circle cx="232" cy="32" r="3" fill={C.accent} />
            </svg>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginTop: 16, padding: 12, border: `1px solid ${C.accent}59`, borderRadius: 4, background: `${C.accent900}66` }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: C.accent, marginTop: 5, flex: "none" }} />
              <p style={{ margin: 0, fontSize: 13.5, lineHeight: "20px", color: C.text }}>
                <span style={{ color: C.accent300 }}>tradezer:</span> ECB jestřábí tón — tenhle typ zprávy historicky +0,3 % do 4 h. Směr ↑, pravděpodobnost 78 %.
              </p>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 16 }}>
              <button type="button" style={{ fontFamily: FONT, fontSize: 14, padding: "9px 0", borderRadius: 4, cursor: "pointer", background: "transparent", border: `1px solid ${C.buy}`, color: C.buy }}>BUY · LONG</button>
              <button type="button" style={{ fontFamily: FONT, fontSize: 14, padding: "9px 0", borderRadius: 4, cursor: "pointer", background: "transparent", border: `1px solid ${C.sell}`, color: C.sell }}>SELL · SHORT</button>
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section style={{ background: `radial-gradient(900px 420px at 85% -40%, ${C.sectionGlow}b3, transparent 64%), ${C.section}`, padding: "70px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 clamp(20px,5vw,72px)", display: "grid", gridTemplateColumns: "repeat(4,auto)", justifyContent: "space-between", gap: "42px 28px" }}>
          <Stat big="5 min" label="Od zprávy k predikci" />
          <Stat big="5" label="Placených datových zdrojů" />
          <Stat big="24/7" label="Nikdy nespím" />
          <Stat big="1" label="Výhoda, kterou ostatní nemají" />
        </div>
      </section>

      {/* Features */}
      <section id="funkce" style={{ maxWidth: 1200, margin: "0 auto", padding: "88px clamp(20px,5vw,72px) 60px" }}>
        <span style={{ display: "block", fontSize: 13, letterSpacing: "0.06em", textTransform: "uppercase", color: C.accent, marginBottom: 14 }}>Co se mnou získáš</span>
        <div style={{ borderTop: "none" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(48px,120px) minmax(0,420px) minmax(0,1fr)", gap: "20px clamp(24px,4vw,72px)", alignItems: "baseline", padding: "34px 0" }}>
            <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 15, color: C.accent, margin: 0 }}>01</p>
            <h2 style={{ fontFamily: FONT, fontWeight: 500, fontSize: 24, lineHeight: "28px", margin: 0, color: C.text }}>Zprávy čtu dřív než trh</h2>
            <p style={{ fontSize: 15.5, lineHeight: "28px", margin: 0, color: "rgba(233,233,237,0.78)", maxWidth: "52ch" }}>Makro kalendář, zpravodajské feedy i tržní data z placených zdrojů stahuju každých pár minut a každou zprávu okamžitě klasifikuju. Zatímco ostatní čtou, co se stalo, ty už víš, co to pravděpodobně udělá s cenou.</p>
          </div>
          <Feature n="02" title="Pravděpodobnosti, ne názory" body="Každá zpráva dostane pravděpodobnost směru — nahoru, dolů, neutrál — zkombinovanou s tím, jak trh na stejný typ zpráv reagoval historicky. Žádné „možná“. Když si nejsem jistý, uvidíš to v čísle." />
          <Feature n="03" title="Přesnost si ověříš sám" body="Každá predikce zůstává v historii vedle toho, co trh skutečně udělal. Denní souhrn pro tradery, dlouhodobé trendy a valuace pro investory — a moje úspěšnost černá na bílém, za 90 dní zpětně." />
        </div>
      </section>

      {/* Demo */}
      <section id="ukazka" style={{ maxWidth: 1200, margin: "0 auto", padding: "48px clamp(20px,5vw,72px) 88px", display: "grid", gridTemplateColumns: "minmax(0,5fr) minmax(0,7fr)", gap: "28px clamp(24px,5vw,96px)", alignItems: "center" }} className="tz-demo-grid">
        <div>
          <span style={{ display: "block", fontSize: 13, letterSpacing: "0.06em", textTransform: "uppercase", color: C.accent, marginBottom: 14 }}>Jak myslím</span>
          <h2 style={{ fontFamily: FONT, fontWeight: 500, fontSize: 32, lineHeight: "42px", margin: 0, color: C.text }}>Nehádám. Počítám.</h2>
          <p style={{ fontSize: 15.5, lineHeight: "28px", color: "rgba(233,233,237,0.78)", margin: "28px 0 0", maxWidth: "48ch" }}>Každý bod v poli je zpráva nebo datový signál. AI klasifikaci vážím historickou reakcí trhu na stejný typ událostí — čím víc dat, tím víc rozhoduje statistika. Tohle není magie, je to kalibrovaná pravděpodobnost.</p>
        </div>
        <div style={{ position: "relative", minHeight: 340, border: `1px solid ${C.n800}`, borderRadius: 8, overflow: "hidden", background: "rgba(0,0,0,0.18)" }}>
          <canvas ref={demoCanvas} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
          <div style={{ position: "absolute", left: 16, bottom: 14, display: "flex", alignItems: "center", gap: 8, fontSize: 12, letterSpacing: "0.06em", textTransform: "uppercase", color: C.n300 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: C.accent }} /> Živé signálové pole
          </div>
        </div>
      </section>

      {/* Quote */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "0 clamp(20px,5vw,72px) 88px" }}>
        <blockquote style={{ fontFamily: FONT, fontWeight: 500, fontSize: "clamp(24px,2.6vw,34px)", lineHeight: "42px", maxWidth: "32ch", margin: 0, color: C.text }}>„Dřív jsem měl otevřených osm záložek a stejně jsem byl poslední, kdo to viděl. Teď mám otevřenou jednu.“</blockquote>
        <p style={{ fontSize: 15.5, color: "rgba(233,233,237,0.64)", margin: "28px 0 0" }}>— trader z uzavřené bety</p>
      </section>

      {/* Přístup / registrace */}
      <section id="pristup" style={{ maxWidth: 1200, margin: "0 auto", padding: "70px clamp(20px,5vw,72px) 56px", borderTop: `1px solid ${C.n800}` }}>
        <h3 style={{ fontFamily: FONT, fontWeight: 500, fontSize: 24, margin: 0, color: C.text }}>Trh nečeká. Ty už nemusíš.</h3>
        <p style={{ fontSize: 15.5, lineHeight: "28px", color: "rgba(233,233,237,0.78)", margin: "24px 0 0", maxWidth: "58ch" }}>Vytvoř si účet a od první minuty vidíš živé predikce, denní souhrn i moji úspěšnost. Feed platím já — ty jen sbíráš náskok.</p>
        <form onSubmit={(e) => { e.preventDefault(); goRegister(); }} style={{ display: "flex", gap: 8, alignItems: "stretch", maxWidth: 480, marginTop: 24 }}>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="tvuj@email.cz" aria-label="E-mail"
            style={{ flex: 1, minHeight: 40, padding: "6px 12px", fontSize: 14, color: C.text, background: C.surface, border: `1px solid rgba(233,233,237,0.16)`, borderRadius: 8, outline: "none" }} />
          <button type="submit" style={{ ...btn, minHeight: 40, color: C.accent, border: `1px solid ${C.accent}` }}>Vytvořit účet</button>
        </form>
      </section>

      <footer style={{ maxWidth: 1200, margin: "0 auto", padding: "56px clamp(20px,5vw,72px)", fontSize: 13, lineHeight: "28px", color: "rgba(233,233,237,0.55)" }}>
        tradezer.app — AI, se kterou se nehádáš. Obchodování nese riziko; výhoda ho jen zmenšuje.
      </footer>

      <style>{`
        @media (max-width: 900px) {
          .tz-hero-grid { grid-template-columns: 1fr !important; }
          .tz-demo-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}
