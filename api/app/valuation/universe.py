"""Univerzum tickerů a skupiny — konfigurovatelné přes .env, s rozumnými defaulty.

DISPLAY_UNIVERSE = firmy, které se zobrazují (top 10 NDX).
PEER_UNIVERSE   = široký vzorek jen pro sektorové statistiky (medián/MAD, z-score).
Míchat tyto dvě je chyba — viz sekce 3 specu.
"""
import os

# ---- Skupiny (seed do val_groups) --------------------------------------------
GROUPS: list[dict] = [
    {"key": "tech",           "label_cs": "Technologie a software",     "label_en": "Technology & Software",   "color_hex": "#3b82f6", "sort_order": 1},
    {"key": "semis",          "label_cs": "Polovodiče",                 "label_en": "Semiconductors",          "color_hex": "#06b6d4", "sort_order": 2},
    {"key": "comms",          "label_cs": "Média a komunikace",         "label_en": "Media & Communications",  "color_hex": "#8b5cf6", "sort_order": 3},
    {"key": "healthcare",     "label_cs": "Farmacie a zdravotnictví",   "label_en": "Healthcare",              "color_hex": "#10b981", "sort_order": 4},
    {"key": "finance",        "label_cs": "Finance a banky",            "label_en": "Financials",              "color_hex": "#eab308", "sort_order": 5},
    {"key": "staples",        "label_cs": "Potraviny a spotřební zboží","label_en": "Consumer Staples",        "color_hex": "#84cc16", "sort_order": 6},
    {"key": "discretionary",  "label_cs": "Zbytné zboží a retail",      "label_en": "Consumer Discretionary",  "color_hex": "#f97316", "sort_order": 7},
    {"key": "energy",         "label_cs": "Energetika",                 "label_en": "Energy",                  "color_hex": "#ef4444", "sort_order": 8},
    {"key": "materials",      "label_cs": "Komodity a materiály",       "label_en": "Materials",               "color_hex": "#a16207", "sort_order": 9},
    {"key": "realestate",     "label_cs": "Nemovitosti",                "label_en": "Real Estate",             "color_hex": "#ec4899", "sort_order": 10},
    {"key": "utilities",      "label_cs": "Utility",                    "label_en": "Utilities",               "color_hex": "#14b8a6", "sort_order": 11},
    {"key": "industrials",    "label_cs": "Průmysl",                    "label_en": "Industrials",             "color_hex": "#64748b", "sort_order": 12},
]

# ---- GICS sektor -> skupina + override pro polovodiče ------------------------
GICS_SECTOR_TO_GROUP: dict[str, str] = {
    "Information Technology": "tech",
    "Technology": "tech",
    "Communication Services": "comms",
    "Health Care": "healthcare",
    "Healthcare": "healthcare",
    "Financials": "finance",
    "Financial Services": "finance",
    "Consumer Staples": "staples",
    "Consumer Defensive": "staples",
    "Consumer Discretionary": "discretionary",
    "Consumer Cyclical": "discretionary",
    "Energy": "energy",
    "Basic Materials": "materials",
    "Materials": "materials",
    "Real Estate": "realestate",
    "Utilities": "utilities",
    "Industrials": "industrials",
}

# Polovodiče se oddělují od techu záměrně (jiná cykličnost i násobky).
SEMICONDUCTOR_TICKERS: set[str] = {
    "NVDA", "AVGO", "AMD", "INTC", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC",
    "ADI", "MRVL", "NXPI", "MCHP", "ON", "MPWR", "SWKS", "QRVO", "TER", "ENTG",
    "ASML", "TSM", "ARM",
}

# Explicitní override skupiny pro jednotlivé tickery (výjimky z GICS).
GROUP_OVERRIDE: dict[str, str] = {t: "semis" for t in SEMICONDUCTOR_TICKERS}


def resolve_group(ticker: str, gics_sector: str | None, gics_industry: str | None) -> str | None:
    """Vrátí group_key: override > semis dle industry > GICS sektor."""
    if ticker in GROUP_OVERRIDE:
        return GROUP_OVERRIDE[ticker]
    if gics_industry and "semiconductor" in gics_industry.lower():
        return "semis"
    if gics_sector:
        return GICS_SECTOR_TO_GROUP.get(gics_sector.strip())
    return None


# ---- Univerza (starter sady, ověřuj váhy při běhu) --------------------------
_DISPLAY_DEFAULT = ["NVDA", "MSFT", "AAPL", "AMZN", "AVGO", "META", "GOOGL", "TSLA", "NFLX", "COST"]

# Široký peer vzorek: NDX100 jádro + zástupci sektorových ETF (XLV/XLE/XLP/XLRE/XLF/XLI/XLU),
# aby sektorové z-score stálo na dostatečně širokém a diverzifikovaném základu.
_PEER_DEFAULT = [
    # NDX / big tech + semis
    "NVDA", "MSFT", "AAPL", "AMZN", "AVGO", "META", "GOOGL", "GOOG", "TSLA", "NFLX",
    "AMD", "QCOM", "TXN", "INTC", "MU", "AMAT", "LRCX", "KLAC", "ADI", "MRVL",
    "NXPI", "MCHP", "ON", "ASML", "ARM", "CRM", "ADBE", "ORCL", "CSCO", "ACN",
    "IBM", "NOW", "INTU", "PANW", "SNPS", "CDNS", "FTNT", "CRWD", "ADSK", "WDAY",
    "TEAM", "DDOG", "ANET", "APH", "GLW",
    # Communication services
    "CMCSA", "DIS", "T", "VZ", "TMUS", "CHTR", "WBD", "EA", "TTWO", "OMC",
    # Healthcare (XLV)
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "AMGN",
    "BMY", "GILD", "ISRG", "VRTX", "REGN", "MDT", "CVS", "CI", "HUM", "ZTS",
    "BSX", "SYK", "BDX",
    # Financials (XLF)
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SPGI",
    "BLK", "SCHW", "C", "CB", "PGR", "MMC", "PNC", "USB", "PYPL", "FI",
    # Consumer staples (XLP)
    "COST", "WMT", "PG", "KO", "PEP", "MDLZ", "PM", "MO", "CL", "KMB",
    "GIS", "KHC", "STZ", "KDP", "MNST", "SYY", "ADM", "KR",
    # Consumer discretionary
    "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "CMG", "MAR", "ORLY",
    "ROST", "YUM", "GM", "F", "LULU", "AZO",
    # Energy (XLE)
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY", "WMB", "KMI",
    "VLO", "HES", "DVN", "HAL", "BKR",
    # Industrials (XLI)
    "GE", "CAT", "RTX", "HON", "UNP", "BA", "DE", "LMT", "UPS", "ETN",
    "GD", "NOC", "EMR", "CSX", "ITW", "MMM", "FDX",
    # Materials (XLB)
    "LIN", "SHW", "APD", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "PPG",
    # Real estate (XLRE)
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "SPG", "WELL", "DLR", "VICI",
    # Utilities (XLU)
    "NEE", "SO", "DUK", "SRE", "AEP", "D", "EXC", "XEL", "PEG", "ED",
]


def _from_env(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def display_universe() -> list[str]:
    return _from_env("VAL_DISPLAY_UNIVERSE", _DISPLAY_DEFAULT)


def peer_universe() -> list[str]:
    # DISPLAY je vždy podmnožinou PEER
    peers = _from_env("VAL_PEER_UNIVERSE", _PEER_DEFAULT)
    for t in display_universe():
        if t not in peers:
            peers.append(t)
    return peers
