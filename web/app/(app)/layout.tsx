import { Plus_Jakarta_Sans } from "next/font/google";
import { Sidebar, MobileNav, AppTopbar } from "@/components/Sidebar";
import { Footer } from "@/components/Footer";
import { HelpChat } from "@/components/HelpChat";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";

const jakarta = Plus_Jakarta_Sans({ subsets: ["latin", "latin-ext"], display: "swap" });

// Chrome přihlášené/aplikační části ve skleněném motivu (.tz-glass, viz globals.css):
// plovoucí menu vlevo, pilulková lišta nahoře a jedna velká skleněná plocha s obsahem.
// Landing na `/` a auth stránky ho nemají.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`tz-glass flow-root ${jakarta.className}`}>
      {/* Zvolený barevný motiv (ThemePicker) nastavit dřív, než se obsah vykreslí. */}
      <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      <MobileNav />
      <div className="flex gap-5 p-3 md:p-5">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col gap-5">
          <AppTopbar />
          <main className="tz-pane min-w-0 rounded-[24px] px-4 py-5 md:rounded-[30px] md:px-7 md:py-7">
            {children}
          </main>
          <div className="w-full px-2 [&>footer]:mt-0 [&>footer]:border-0 [&>footer]:pt-0">
            <Footer />
          </div>
        </div>
      </div>
      <HelpChat />
    </div>
  );
}
