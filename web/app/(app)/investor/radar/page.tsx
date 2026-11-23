"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Radar firem je teď součástí Přehledu (sekce #radar) — stará adresa přesměruje.
export default function InvestorRadarRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/investor#radar"); }, [router]);
  return <div className="h-40 animate-pulse rounded-2xl bg-panel" />;
}
