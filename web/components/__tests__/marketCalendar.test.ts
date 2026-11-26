import { describe, expect, it } from "vitest";
import { dayStatus, localDate, upcomingSpecialDays } from "@/lib/marketCalendar";

describe("marketCalendar", () => {
  it("Díkůvzdání: NY zavřeno, Londýn otevřeno", () => {
    expect(dayStatus("New York", "2026-11-26")).toEqual({ closed: true, reason: "Díkůvzdání" });
    expect(dayStatus("London", "2026-11-26")).toEqual({ closed: false });
  });

  it("zkrácený den a víkend", () => {
    expect(dayStatus("New York", "2026-11-27")).toMatchObject({ closed: false, earlyClose: 13 });
    expect(dayStatus("Tokyo", "2026-11-28")).toEqual({ closed: true, reason: "víkend" });
  });

  it("místní datum burzy podle časové zóny", () => {
    const d = new Date("2026-11-26T23:30:00Z");          // v Tokiu už je pátek ráno
    expect(localDate("Asia/Tokyo", d)).toBe("2026-11-27");
    expect(localDate("America/New_York", d)).toBe("2026-11-26");
  });

  it("nadcházející svátky bez víkendů, seřazené", () => {
    const up = upcomingSpecialDays("2026-11-26", 14);
    expect(up.map((u) => `${u.date} ${u.market} ${u.closed}`)).toEqual([
      "2026-11-26 New York true",
      "2026-11-27 New York false",
    ]);
  });
});
