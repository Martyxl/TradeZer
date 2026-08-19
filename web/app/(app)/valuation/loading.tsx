import { Loader2 } from "lucide-react";

// Okamžitá odezva při přechodu na /valuation (než se načte bundle + první data).
export default function ValuationLoading() {
  return (
    <div className="flex h-[70vh] flex-col items-center justify-center gap-3 text-gray-400">
      <Loader2 size={30} className="animate-spin text-blue-400" />
      <div className="text-sm font-medium text-gray-300">Načítám Valuation Radar…</div>
    </div>
  );
}
