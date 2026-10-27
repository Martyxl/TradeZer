//+------------------------------------------------------------------+
//| Tradezer_BiasEA.mq5                                              |
//| Denní bias z Tradezeru → po NY open limit s offsetem proti biasu |
//| → drženo do NY close. Pro FTMO (MT5), primárně DEMO / Free Trial. |
//|                                                                  |
//| Zdroj plánu: GET {InpApiBase}/api/ea/plan?ticker=NQ (text k=v)   |
//| NUTNÉ: Nástroje → Možnosti → Poradci → povolit WebRequest pro    |
//|        https://tradezer.app                                      |
//| Strategy Tester WebRequest nepodporuje → testovat forward na demo.|
//+------------------------------------------------------------------+
#property copyright "Tradezer"
#property version   "1.00"
#property description "Bias po London open → limit s offsetem po NY open → drž do close. FTMO news guard ±N min."

#include <Trade\Trade.mqh>

//--- vstupy
input string InpApiBase           = "https://tradezer.app";
input string InpTickers           = "NQ=US100.cash;ES=US500.cash;YM=US30.cash;XAUUSD=XAUUSD"; // Tradezer ticker = symbol u brokera
input double InpRiskPct           = 0.25;    // riziko na obchod (% zůstatku) při zásahu SL
input double InpStopMult          = 2.0;     // SL = offset × násobek (za vstupní cenou)
input double InpMinTrust          = 0.0;     // minimální trust biasu (0 = bez filtru)
input int    InpEntryWindowMin    = 15;      // zadat limit do N minut po NY open
input string InpCancelUtc         = "19:00"; // nevyplněné limity zrušit (UTC)
input string InpCloseUtc          = "20:50"; // otevřené pozice zavřít (UTC), před denní přestávkou
input int    InpNewsBufferMin     = 3;       // FTMO: žádné provedení ±N min kolem high-impact zpráv
input bool   InpTradeWithoutNews  = false;   // obchodovat i když kalendář zpráv není dostupný
input double InpDailyLossStopPct  = 2.0;     // pojistka: ztráta za den v % → vše zavřít a do zítřka stát
input long   InpMagic             = 260423;
input bool   InpDryRun            = true;    // jen logovat, neobchodovat (nejdřív nechat běžet takhle)

//--- stav po tickerech
#define MAXT 8
int      g_n = 0;
string   g_ticker[MAXT], g_symbol[MAXT], g_dir[MAXT];
double   g_trust[MAXT], g_offset[MAXT], g_entry[MAXT], g_sl[MAXT], g_vol[MAXT];
bool     g_newsOk[MAXT], g_planOk[MAXT], g_placed[MAXT], g_removedForNews[MAXT], g_finished[MAXT];
int      g_type[MAXT];                 // 0 = buy limit, 1 = sell limit
datetime g_newsTime[];                 // ploché pole časů zpráv (UTC)
int      g_newsIdx[];                  // ke kterému tickeru zpráva patří

string   g_day = "";
double   g_dayStartEquity = 0;
bool     g_dayStopped = false;
datetime g_lastPlanFetch = 0;
CTrade   trade;

//+------------------------------------------------------------------+
int MinutesOf(const string hhmm)
  {
   string p[];
   if(StringSplit(hhmm, ':', p) != 2) return -1;
   return (int)StringToInteger(p[0]) * 60 + (int)StringToInteger(p[1]);
  }

int UtcMinutes(const datetime t)
  {
   MqlDateTime s; TimeToStruct(t, s);
   return s.hour * 60 + s.min;
  }

string UtcDay(const datetime t)
  {
   string d = TimeToString(t, TIME_DATE);   // 2026.10.23
   StringReplace(d, ".", "-");
   return d;
  }

void Log(const string ticker, const string event, const string details)
  {
   string line = TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS) + " UTC | " + ticker + " | " + event + " | " + details;
   Print(line);
   int h = FileOpen("tradezer_ea_log.csv", FILE_READ | FILE_WRITE | FILE_TXT | FILE_UNICODE | FILE_SHARE_READ);
   if(h != INVALID_HANDLE)
     {
      FileSeek(h, 0, SEEK_END);
      FileWriteString(h, line + "\r\n");
      FileClose(h);
     }
  }

string HttpGet(const string url)
  {
   char data[], result[];
   string headers;
   ResetLastError();
   int code = WebRequest("GET", url, "", 10000, data, result, headers);
   if(code != 200)
     {
      Log("-", "HTTP", StringFormat("%d %s (chyba %d — povolen WebRequest pro %s?)", code, url, GetLastError(), InpApiBase));
      return "";
     }
   return CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
  }

datetime ParseIsoUtc(string iso)              // 2026-10-23T14:00:00Z → datetime (UTC)
  {
   StringReplace(iso, "T", " ");
   StringReplace(iso, "Z", "");
   StringReplace(iso, "-", ".");
   return StringToTime(iso);
  }

//+------------------------------------------------------------------+
bool FetchPlan(const int i)
  {
   string body = HttpGet(InpApiBase + "/api/ea/plan?ticker=" + g_ticker[i]);
   if(body == "") return false;
   string lines[];
   int n = StringSplit(body, '\n', lines);
   string date = "";
   g_dir[i] = "none"; g_trust[i] = 0; g_offset[i] = 0; g_newsOk[i] = false;
   // smaž staré zprávy tohoto tickeru
   int keep = 0;
   for(int k = 0; k < ArraySize(g_newsTime); k++)
      if(g_newsIdx[k] != i) { g_newsTime[keep] = g_newsTime[k]; g_newsIdx[keep] = g_newsIdx[k]; keep++; }
   ArrayResize(g_newsTime, keep); ArrayResize(g_newsIdx, keep);

   for(int k = 0; k < n; k++)
     {
      string ln = lines[k];
      StringTrimRight(ln); StringTrimLeft(ln);
      int eq = StringFind(ln, "=");
      if(eq < 1) continue;
      string key = StringSubstr(ln, 0, eq), val = StringSubstr(ln, eq + 1);
      if(key == "date") date = val;
      else if(key == "direction") g_dir[i] = val;
      else if(key == "trust") g_trust[i] = StringToDouble(val);
      else if(key == "offset_pct") g_offset[i] = StringToDouble(val);
      else if(key == "news_ok") g_newsOk[i] = (val == "1");
      else if(key == "news")
        {
         string parts[];
         if(StringSplit(val, '|', parts) >= 1)
           {
            int m = ArraySize(g_newsTime);
            ArrayResize(g_newsTime, m + 1); ArrayResize(g_newsIdx, m + 1);
            g_newsTime[m] = ParseIsoUtc(parts[0]); g_newsIdx[m] = i;
           }
        }
     }
   if(date != g_day)
     {
      Log(g_ticker[i], "PLAN", "plán je pro jiný den (" + date + " vs " + g_day + ") — čekám");
      return false;
     }
   int cnt = 0;
   for(int k = 0; k < ArraySize(g_newsIdx); k++) if(g_newsIdx[k] == i) cnt++;
   Log(g_ticker[i], "PLAN", StringFormat("směr=%s trust=%.1f offset=%.3f%% zprávy=%d news_ok=%d",
       g_dir[i], g_trust[i], g_offset[i], cnt, (int)g_newsOk[i]));
   return true;
  }

bool InNewsWindow(const int i, const datetime nowUtc)
  {
   for(int k = 0; k < ArraySize(g_newsTime); k++)
      if(g_newsIdx[k] == i && MathAbs((double)(nowUtc - g_newsTime[k])) <= InpNewsBufferMin * 60)
         return true;
   return false;
  }

//+------------------------------------------------------------------+
double NormPrice(const string sym, const double p)
  {
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   if(ts > 0) return NormalizeDouble(MathRound(p / ts) * ts, digits);
   return NormalizeDouble(p, digits);
  }

double CalcVolume(const string sym, const double stopDist)
  {
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tv <= 0) tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0 || stopDist <= 0) return 0;
   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0;
   double vol = riskMoney / (stopDist / ts * tv);
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = 0.01;
   vol = MathFloor(vol / step) * step;
   if(vol < vmin) return 0;
   return MathMin(vol, vmax);
  }

bool HasPending(const int i, ulong &ticket)
  {
   for(int k = OrdersTotal() - 1; k >= 0; k--)
     {
      ulong t = OrderGetTicket(k);
      if(t > 0 && OrderGetString(ORDER_SYMBOL) == g_symbol[i] && OrderGetInteger(ORDER_MAGIC) == InpMagic)
        { ticket = t; return true; }
     }
   return false;
  }

bool HasPosition(const int i)
  {
   for(int k = PositionsTotal() - 1; k >= 0; k--)
     {
      ulong t = PositionGetTicket(k);
      if(t > 0 && PositionGetString(POSITION_SYMBOL) == g_symbol[i] && PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
     }
   return false;
  }

void DeletePending(const int i, const string why)
  {
   if(InpDryRun) { Log(g_ticker[i], "ZRUŠENO (dry-run)", why); return; }
   ulong t;
   while(HasPending(i, t))
     {
      if(trade.OrderDelete(t)) Log(g_ticker[i], "ZRUŠENO", why);
      else { Log(g_ticker[i], "CHYBA", "zrušení limitu selhalo: " + trade.ResultRetcodeDescription()); break; }
     }
  }

void ClosePositions(const int i, const string why)
  {
   for(int k = PositionsTotal() - 1; k >= 0; k--)
     {
      ulong t = PositionGetTicket(k);
      if(t == 0 || PositionGetString(POSITION_SYMBOL) != g_symbol[i] || PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      double pnl = PositionGetDouble(POSITION_PROFIT);
      if(InpDryRun || trade.PositionClose(t)) Log(g_ticker[i], "ZAVŘENO", StringFormat("%s, P/L %.2f", why, pnl));
      else Log(g_ticker[i], "CHYBA", "zavření selhalo: " + trade.ResultRetcodeDescription());
     }
  }

bool PlaceLimit(const int i)
  {
   string sym = g_symbol[i];
   if(g_vol[i] <= 0) return false;
   bool ok;
   if(InpDryRun)
      ok = true;
   else if(g_type[i] == 0)
      ok = trade.BuyLimit(g_vol[i], g_entry[i], sym, g_sl[i], 0, ORDER_TIME_GTC, 0, "Tradezer bias");
   else
      ok = trade.SellLimit(g_vol[i], g_entry[i], sym, g_sl[i], 0, ORDER_TIME_GTC, 0, "Tradezer bias");
   Log(g_ticker[i], ok ? (InpDryRun ? "LIMIT (dry-run)" : "LIMIT") : "CHYBA",
       StringFormat("%s %.2f lot @ %s SL %s%s", g_type[i] == 0 ? "BUY" : "SELL", g_vol[i],
                    DoubleToString(g_entry[i], (int)SymbolInfoInteger(sym, SYMBOL_DIGITS)),
                    DoubleToString(g_sl[i], (int)SymbolInfoInteger(sym, SYMBOL_DIGITS)),
                    ok ? "" : " — " + trade.ResultRetcodeDescription()));
   return ok;
  }

void PrepareAndPlace(const int i)
  {
   string sym = g_symbol[i];
   int sign = (g_dir[i] == "up") ? 1 : -1;
   double bid = SymbolInfoDouble(sym, SYMBOL_BID), ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(bid <= 0 || ask <= 0) { Log(g_ticker[i], "ČEKÁ", "bez ceny"); return; }
   double ref = (bid + ask) / 2.0;
   double entry = ref * (1.0 - sign * g_offset[i] / 100.0);
   double sl = entry * (1.0 - sign * g_offset[i] * InpStopMult / 100.0);
   g_entry[i] = NormPrice(sym, entry);
   g_sl[i] = NormPrice(sym, sl);
   g_type[i] = (sign > 0) ? 0 : 1;
   g_vol[i] = CalcVolume(sym, MathAbs(g_entry[i] - g_sl[i]));
   if(g_vol[i] <= 0)
     {
      Log(g_ticker[i], "PŘESKOČENO", "objem pod minimem (riziko příliš malé pro daný SL)");
      g_finished[i] = true;
      return;
     }
   if(PlaceLimit(i)) g_placed[i] = true; else g_finished[i] = true;
  }

//+------------------------------------------------------------------+
void NewDay(const string day)
  {
   g_day = day;
   g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayStopped = false;
   g_lastPlanFetch = 0;
   for(int i = 0; i < g_n; i++)
     {
      g_planOk[i] = false; g_placed[i] = false; g_removedForNews[i] = false; g_finished[i] = false;
      g_dir[i] = "none"; g_vol[i] = 0;
     }
   ArrayResize(g_newsTime, 0); ArrayResize(g_newsIdx, 0);
   Log("-", "NOVÝ DEN", StringFormat("%s, equity %.2f", day, g_dayStartEquity));
  }

// US letní čas: od 2. neděle v březnu do 1. neděle v listopadu (přechod v 2:00 ET ≈ 7:00 UTC).
// NY cash open 9:30 ET = 13:30 UTC v létě, 14:30 UTC v zimě.
datetime NthSundayUtc(int year, int mon, int nth)
  {
   MqlDateTime d; d.year = year; d.mon = mon; d.day = 1; d.hour = 7; d.min = 0; d.sec = 0;
   datetime first = StructToTime(d);
   MqlDateTime f; TimeToStruct(first, f);
   int add = (7 - f.day_of_week) % 7 + 7 * (nth - 1);
   return first + add * 86400;
  }

int NyOpenUtcMinutes(datetime nowUtc)
  {
   MqlDateTime s; TimeToStruct(nowUtc, s);
   bool dst = nowUtc >= NthSundayUtc(s.year, 3, 2) && nowUtc < NthSundayUtc(s.year, 11, 1);
   return (dst ? 13 : 14) * 60 + 30;
  }

void OnTimer()
  {
   datetime now = TimeGMT();
   MqlDateTime s; TimeToStruct(now, s);
   if(s.day_of_week == 0 || s.day_of_week == 6) return;          // víkend
   string day = UtcDay(now);
   if(day != g_day) NewDay(day);

   int m = UtcMinutes(now);
   int nyOpen = NyOpenUtcMinutes(now), cancelM = MinutesOf(InpCancelUtc), closeM = MinutesOf(InpCloseUtc);

   // pojistka denní ztráty
   if(!g_dayStopped && g_dayStartEquity > 0 &&
      AccountInfoDouble(ACCOUNT_EQUITY) <= g_dayStartEquity * (1.0 - InpDailyLossStopPct / 100.0))
     {
      g_dayStopped = true;
      for(int i = 0; i < g_n; i++) { DeletePending(i, "denní ztráta"); ClosePositions(i, "denní ztráta"); }
      Log("-", "STOP", "dosažena denní ztráta, do zítřka neobchoduji");
     }

   // plán: stáhnout 10 min před NY open (bias je z London open), opakovat každou minutu dokud se nepovede
   if(m >= nyOpen - 10 && m < nyOpen + InpEntryWindowMin && now - g_lastPlanFetch >= 60)
     {
      g_lastPlanFetch = now;
      for(int i = 0; i < g_n; i++) if(!g_planOk[i]) g_planOk[i] = FetchPlan(i);
     }

   for(int i = 0; i < g_n; i++)
     {
      bool news = InNewsWindow(i, now);
      ulong pend;
      bool hasPend = HasPending(i, pend) || (InpDryRun && g_placed[i] && !g_finished[i] && !g_removedForNews[i]);

      // 1) zadání limitu po NY open
      if(!g_dayStopped && g_planOk[i] && !g_placed[i] && !g_finished[i] && m >= nyOpen && m < nyOpen + InpEntryWindowMin)
        {
         if(g_dir[i] != "up" && g_dir[i] != "down") { Log(g_ticker[i], "BEZ OBCHODU", "směr " + g_dir[i]); g_finished[i] = true; }
         else if(g_trust[i] < InpMinTrust) { Log(g_ticker[i], "BEZ OBCHODU", StringFormat("trust %.1f < %.1f", g_trust[i], InpMinTrust)); g_finished[i] = true; }
         else if(!g_newsOk[i] && !InpTradeWithoutNews) { Log(g_ticker[i], "BEZ OBCHODU", "kalendář zpráv nedostupný"); g_finished[i] = true; }
         else if(g_offset[i] <= 0) { Log(g_ticker[i], "BEZ OBCHODU", "chybí offset"); g_finished[i] = true; }
         else if(!news) PrepareAndPlace(i);
        }

      // 2) FTMO news guard: limit nesmí být aktivní kolem zprávy (fill = provedení)
      if(news && hasPend && !HasPosition(i))
        {
         DeletePending(i, "zpráva ±" + IntegerToString(InpNewsBufferMin) + " min");
         g_removedForNews[i] = true;
        }
      // 3) po zprávě limit obnovit (pokud ještě platí den a nic není otevřené)
      if(!news && g_removedForNews[i] && !g_dayStopped && m < cancelM && !HasPosition(i))
        {
         g_removedForNews[i] = false;
         if(!PlaceLimit(i)) g_finished[i] = true;
        }

      // 4) zrušit nevyplněný limit
      if(m >= cancelM && g_placed[i] && !g_finished[i] && !HasPosition(i))
        {
         DeletePending(i, "nevyplněno do " + InpCancelUtc + " UTC");
         g_finished[i] = true;
        }
      // 5) zavřít pozice (ne uprostřed news okna)
      if(m >= closeM && !news && HasPosition(i)) ClosePositions(i, "konec dne " + InpCloseUtc + " UTC");
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   string pairs[];
   int n = StringSplit(InpTickers, ';', pairs);
   g_n = 0;
   for(int k = 0; k < n && g_n < MAXT; k++)
     {
      string kv[];
      if(StringSplit(pairs[k], '=', kv) != 2) continue;
      string sym = kv[1];
      StringTrimLeft(sym); StringTrimRight(sym);
      if(!SymbolSelect(sym, true))
        {
         Print("Tradezer EA: symbol ", sym, " u brokera neexistuje — zkontroluj Market Watch a InpTickers");
         continue;
        }
      g_ticker[g_n] = kv[0];
      StringTrimLeft(g_ticker[g_n]); StringTrimRight(g_ticker[g_n]);
      g_symbol[g_n] = sym;
      g_n++;
     }
   if(g_n == 0) { Print("Tradezer EA: žádný platný symbol"); return INIT_PARAMETERS_INCORRECT; }
   if(MinutesOf(InpCancelUtc) < 0 || MinutesOf(InpCloseUtc) < 0) return INIT_PARAMETERS_INCORRECT;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   EventSetTimer(20);
   Log("-", "START", StringFormat("tickerů %d, riziko %.2f%%, SL %.1f× offset, dry-run=%d, API %s",
       g_n, InpRiskPct, InpStopMult, (int)InpDryRun, InpApiBase));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTick() {}
//+------------------------------------------------------------------+
