"use client";

import { useState } from "react";
import { Heart, X, Copy, Check } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

const ACCOUNT = "107-8153720267/0100";
const IBAN = "CZ3701000001078153720267";
const EUR_IBAN = "LT24 3250 0129 8959 2841"; // Revolut (SEPA)
// Český standard QR platba (SPD) — banka po naskenování předvyplní převod
const QR_PAYMENT = `SPD*1.0*ACC:${IBAN}*CC:CZK*MSG:PODPORA TRADEZER`;

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[#2a2d3a] bg-[#151823] px-3 py-2">
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
        <div className="text-sm text-white font-mono truncate">{value}</div>
      </div>
      <button
        onClick={copy}
        className="shrink-0 text-gray-400 hover:text-white transition-colors"
        title="Kopírovat"
      >
        {copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} />}
      </button>
    </div>
  );
}

export function SupportButton({ variant = "sidebar" }: { variant?: "sidebar" | "footer" }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      {variant === "sidebar" ? (
        <button
          onClick={() => setOpen(true)}
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-gray-400 hover:text-white hover:bg-[#1a1d27] transition-colors w-full"
        >
          <Heart size={16} className="text-rose-400" />
          Podpořit
        </button>
      ) : (
        <button
          onClick={() => setOpen(true)}
          className="flex items-center gap-1.5 text-gray-500 hover:text-rose-300 transition-colors"
        >
          <Heart size={13} className="text-rose-400" />
          Podpořit projekt
        </button>
      )}

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-sm w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Heart size={18} className="text-rose-400" /> Podpořit Tradezer
              </h2>
              <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-white">
                <X size={18} />
              </button>
            </div>
            <p className="text-xs text-gray-400 mb-4">
              Pokud ti Tradezer pomáhá, můžeš provoz podpořit libovolnou částkou. Díky!
            </p>

            <div className="flex justify-center mb-4">
              <div className="rounded-xl bg-white p-3">
                <QRCodeSVG value={QR_PAYMENT} size={160} level="M" />
              </div>
            </div>
            <p className="text-[10px] text-gray-500 text-center mb-4 -mt-2">
              QR platba — naskenuj v bankovní aplikaci
            </p>

            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-gray-500 pt-1">CZK — bankovní převod</div>
              <CopyRow label="Číslo účtu" value={ACCOUNT} />
              <CopyRow label="IBAN" value={IBAN} />
              <div className="text-[10px] uppercase tracking-wider text-gray-500 pt-2">EUR — Revolut (SEPA)</div>
              <CopyRow label="IBAN" value={EUR_IBAN} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
