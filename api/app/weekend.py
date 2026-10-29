"""Víkendový útlum: trhy jsou zavřené, smyčky na Sparku stojí a Neon smí usnout.

Okno = pátek 17:30 → neděle 16:00 newyorského času (CME zavírá v pátek 17:00 ET, otevírá v neděli 18:00 ET).
Stejné okno používá scripts/spark/weekend_switch.sh a HelpChat.tsx — při změně upravit všechna tři místa.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def is_weekend_quiet(now: datetime | None = None) -> bool:
    t = (now or datetime.now(timezone.utc)).astimezone(_NY)
    hm = t.hour * 100 + t.minute
    dow = t.isoweekday()   # 5 = pátek, 6 = sobota, 7 = neděle
    return (dow == 5 and hm >= 1730) or dow == 6 or (dow == 7 and hm < 1600)


WEEKEND_MSG = ("Pomocník má o víkendu pauzu — trhy jsou zavřené a AI server šetří provoz. "
               "Vrátí se v neděli večer (kolem 21–22 h našeho času). Mezitím mrkni do Legendy.")
