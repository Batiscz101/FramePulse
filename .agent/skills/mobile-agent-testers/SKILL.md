---
name: mobile-agent-testers
description: Spousti a overuje kompletni sadu unit testu PC agenta (pc-agent), typovou kontrolu i testy mobilni aplikace (m) a kontrolu end-to-end kompatibility schematu s Neon databazi.
---

# Mobile & PC Agent Testers

Tento skill pouzij vzdy po uprave kodu v `pc-agent`, `m` nebo `neon/neon_schema.sql`.

## Postup overeni

1. **Testy PC agenta (`C:\f\pc-agent`):**
   - Spust `.venv\Scripts\python.exe -B -m unittest discover -s tests -t . -v`
   - Over, ze prochazi validace payloadu (`LIVE_STATUS_COLUMNS`, `SESSIONS_COLUMNS`, `FPS_SAMPLES_COLUMNS`), cteni senzoru (`sensors.py`, Core Temp / HWiNFO64) i fronta odesilani (`upload.py`).

2. **Testy a typova kontrola mobilni aplikace (`C:\f\m`):**
   - Spust `npx.cmd tsc --noEmit`
   - Pokud existuji unit testy (`package.json` obsahuje `test`), spust `npm test -- --watchAll=false`.
   - Zkontroluj responzivitu grafu (`onLayout` sirka misto pevnych rozmeru) a mapovani sloupcu z Neon Data API (`cpu_temp`, `gpu_temp`, `timestamp_offset`).

3. **Kontrola shody databazoveho schematu:**
   - Porovnej nazvy sloupcu mezi `pc-agent/framepulse_agent/supabase.py`, `m/src/lib/` a `neon/neon_schema.sql`, aby nedoslo k chybe `42703` (chybejici sloupec) ani `23502` (`NOT NULL` na starem sloupci).

4. **Report:**
   - Vypis strucny prehled vysledku (pocet proslych testu, pripadne chyby a zda je nutne prestavit `FramePulseAgent.exe` pres `build_agent.bat`).
