"use client";

import { useEffect, useState } from "react";
import { Eye } from "lucide-react";

export function Footer() {
  const [visits, setVisits] = useState<number | null>(null);

  useEffect(() => {
    // Inkrementuj jednou per session (sessionStorage guard proti reloadům)
    const counted = sessionStorage.getItem("tz_visit_counted");
    const url = counted ? "/api/public/visits" : "/api/public/visit";
    fetch(url, { method: counted ? "GET" : "POST", cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (typeof d.visits === "number") setVisits(d.visits);
        if (!counted) sessionStorage.setItem("tz_visit_counted", "1");
      })
      .catch(() => {});
  }, []);

  return (
    <footer className="mt-12 border-t border-[#2a2d3a] py-5">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-gray-500">
        <span>© {new Date().getFullYear()} BigHead — Tradezer. Všechna práva vyhrazena.</span>
        {visits !== null && (
          <span className="flex items-center gap-1.5">
            <Eye size={13} />
            {visits.toLocaleString("cs")} návštěv
          </span>
        )}
      </div>
    </footer>
  );
}
