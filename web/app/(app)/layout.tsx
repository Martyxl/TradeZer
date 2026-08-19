import { Sidebar, MobileNav } from "@/components/Sidebar";
import { Footer } from "@/components/Footer";

// Chrome přihlášené/aplikační části (sidebar + user menu). Landing na `/` ho nemá.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <MobileNav />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 min-w-0 px-4 py-6 md:px-8">
          <div className="mx-auto max-w-6xl">
            {children}
            <Footer />
          </div>
        </main>
      </div>
    </>
  );
}
