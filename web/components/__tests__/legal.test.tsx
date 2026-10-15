import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));

import { LEGAL } from "@/lib/legal";
import { CookieNotice } from "@/components/CookieNotice";
import { LegalLinks } from "@/components/LegalLinks";
import { ContactEmail, VatNote } from "@/components/LegalLayout";

beforeEach(() => { cleanup(); localStorage.clear(); });

describe("právní údaje", () => {
  it("verze podmínek ve frontendu = verze v backendu (jinak by se ukládal špatný důkaz souhlasu)", () => {
    const py = readFileSync(resolve(__dirname, "../../../api/app/legal.py"), "utf-8");
    expect(py).toContain(`TERMS_VERSION = "${LEGAL.termsVersion}"`);
  });

  it("obsahuje identifikaci provozovatele a patička odkazuje na všechny tři stránky", () => {
    expect(LEGAL.ico).toBe("88916219");
    render(<LegalLinks />);
    for (const href of ["/obchodni-podminky", "/ochrana-osobnich-udaju", "/cookies"]) {
      expect(document.querySelector(`a[href="${href}"]`)).not.toBeNull();
    }
    expect(screen.getByText(/Martin Špatenka, IČO 88916219/)).toBeInTheDocument();
  });

  it("nevyplněný e-mail a DPH jsou na stránce VIDITELNĚ označené k doplnění (ať se nezapomene)", () => {
    if (!LEGAL.email) {
      render(<ContactEmail />);
      expect(screen.getByText(/doplnit kontaktní e-mail/)).toBeInTheDocument();
    }
    if (LEGAL.vatPayer === null) {
      render(<VatNote />);
      expect(screen.getByText(/plátce \/ neplátce DPH/)).toBeInTheDocument();
    } else if (LEGAL.vatPayer) {
      render(<VatNote />);
      expect(screen.getByText(/Provozovatel je plátcem DPH/)).toBeInTheDocument();
    }
  });
});

describe("CookieNotice", () => {
  it("zobrazí se poprvé, po „Rozumím“ zmizí a už se nevrací", () => {
    const { unmount } = render(<CookieNotice />);
    expect(screen.getByText(/Žádné sledování ani reklamy/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Rozumím"));
    expect(screen.queryByText(/Žádné sledování ani reklamy/)).toBeNull();
    expect(localStorage.getItem("tz_notice_ok")).toBe("1");
    unmount();
    render(<CookieNotice />);
    expect(screen.queryByText(/Žádné sledování ani reklamy/)).toBeNull();
  });
});
