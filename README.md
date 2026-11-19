# FramePulse

Osobní telemetrie výkonu her. Tichý **Windows agent** měří FPS přes
[PresentMon](https://github.com/GameTechDev/PresentMon), ukládá herní seance do
**Supabase** a **mobilní aplikace** je zobrazuje jako přehledné grafy.

```
┌────────────────────┐   HTTPS/PostgREST   ┌────────────────────┐   HTTPS   ┌────────────────────┐
│      pc-agent      │ ──────────────────► │      Supabase      │ ◄──────── │     mobile-app     │
│ Windows 11 + tray  │                     │ Postgres + RLS     │           │ Expo / React Native│
│ PresentMon → FPS   │                     │ games, sessions,   │           │ seznam + graf FPS  │
└────────────────────┘                     │ fps_samples        │           └────────────────────┘
                                           └────────────────────┘
```

Repozitář je připravený pro **veřejné použití**: neobsahuje žádné skutečné
přístupové údaje. Každý si vytvoří vlastní Supabase projekt a připojí ho podle
návodu níže – konfigurační soubory s reálnými hodnotami zůstávají pouze na disku
a git je ignoruje.

## Co projekt umí

- **Automatická detekce her** – agent každé 2 sekundy kontroluje viditelná okna,
  ignoruje prohlížeče, Discord, Steam apod. Skutečnost, že jde o hru, potvrdí až
  příchozí framy z PresentMonu.
- **Měření bez zásahu** – 2sekundové vzorky pro graf, zahřívací fáze 5 s se
  nepočítá, seance kratší než 15 s se zahazuje.
- **Metriky** – průměrné FPS, **1% low** jako `min_fps` a nejlepší 2s vzorek jako
  `max_fps`.
- **Offline fronta** – nepodařený upload zůstane v `outbox/` a odešle se později;
  zápis je idempotentní, takže nevznikají duplicity.
- **Mobilní přehled** – seznam her s hledáním, detail s přepínačem seancí,
  Avg / Min / Max FPS a interaktivní graf s tooltipem. Čeština i angličtina.
- **Ruční správa** – hru lze v aplikaci přidat nebo přejmenovat i bez agenta.

## Struktura repozitáře

```
FPS_tracker/
├─ pc-agent/                  Windows agent (Python + PresentMon + tray)
│  ├─ framepulse_agent/       zdrojový kód agenta
│  ├─ tests/                  unittest sada
│  ├─ setup.bat               jednorázová instalace (venv, závislosti, PresentMon)
│  ├─ start_agent.bat         spuštění agenta bez konzole
│  ├─ start_agent.pyw         spouštěč pro pythonw / autostart
│  ├─ autostart.py            zapnutí/vypnutí spouštění po přihlášení
│  ├─ config.example.json     vzor konfigurace
│  └─ README.md               podrobný manuál agenta
├─ mobile-app/                Expo aplikace (React Native + TypeScript)
│  ├─ src/app/                obrazovky (Expo Router)
│  ├─ src/components/         karty, graf, modaly, přepínač jazyka
│  ├─ src/hooks/              načítání dat ze Supabase
│  ├─ src/lib/                Supabase klient, API, formátování, i18n, téma
│  └─ README.md               poznámky k aplikaci
├─ supabase_schema.sql        tabulky, indexy, RLS politiky a granty
├─ AGENTS.md                  konvence pro vývoj s AI agenty
└─ .gitignore
```

## Požadavky

| Část | Potřebujete |
| --- | --- |
| Supabase | účet a projekt (free tier stačí) |
| pc-agent | Windows 11, Python 3.10+, oprávnění pro PresentMon |
| mobile-app | Node.js 22.13+ a npm, telefon s **Expo Go** (SDK 58) nebo development build |

## 1. Supabase

1. Vytvořte nový projekt na [supabase.com](https://supabase.com).
2. Otevřete **SQL Editor**, vložte celý obsah [`supabase_schema.sql`](supabase_schema.sql)
   a spusťte. Skript je idempotentní – dá se pustit opakovaně.
3. V **Project Settings → API** si zkopírujte:
   - **Project URL** ve tvaru `https://<project-ref>.supabase.co`,
   - **anon / publishable** klíč (`sb_publishable_…` nebo starší JWT `eyJ…`).

Tyto dvě hodnoty pak vložte na dvě místa:

| Kde | Proměnná / klíč |
| --- | --- |
| `mobile-app/.env.local` | `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_ANON_KEY` |
| `pc-agent/config.json` | `supabase_url`, `supabase_key` |

> V repozitáři jsou pouze ukázkové hodnoty `https://your-project.supabase.co`
> a `your-anon-key`. Skutečné hodnoty nikdy necommitujte.

Vzniknou tři tabulky:

| Tabulka | Obsah |
| --- | --- |
| `games` | hry podle `process_name` (např. `Cyberpunk2077.exe`) |
| `sessions` | jednotlivá hraní: `played_at`, `avg_fps`, `min_fps`, `max_fps`, `duration_seconds` |
| `fps_samples` | časová řada: `timestamp_offset` (s) a `fps` |

> **Klíče:** publishable/anon klíč je veřejný a patří do klienta – data chrání RLS
> politiky. `service_role` / secret klíč nikdy nevkládejte do aplikace ani do gitu.
> Schéma záměrně povoluje roli `anon` plný přístup, protože aplikace se
> nepřihlašuje. Kdo zná URL a anon klíč vašeho projektu, může s daty pracovat –
> pro citlivá data zapněte Supabase Auth a upravte politiky v `supabase_schema.sql`.

## 2. PC agent

Podrobný manuál včetně všech voleb konfigurace je v [`pc-agent/README.md`](pc-agent/README.md).

```bat
cd pc-agent
setup.bat            :: vytvoří .venv, nainstaluje závislosti a stáhne PresentMon
```

`setup.bat` založí z `config.example.json` soubor `config.json` (v gitu je
ignorovaný). **Před prvním spuštěním** v něm nahraďte ukázkové hodnoty:

```json
{
  "supabase_url": "https://<project-ref>.supabase.co",
  "supabase_key": "<anon nebo publishable klíč>"
}
```

Potom agenta spusťte:

```bat
start_agent.bat      :: spustí agenta bez konzolového okna
```

Bez vyplněných údajů agent naběhne, ale upload seancí bude selhávat a seance
zůstanou ve frontě `outbox/`.

### Oprávnění PresentMonu

PresentMon zachytává framy přes ETW. Zvolte jednu z možností:

**A. Skupina `Performance Log Users` (doporučeno, bez UAC)** – v terminálu jako
správce:

```bat
net localgroup "Performance Log Users" %USERNAME% /add
```

Potom se odhlaste a znovu přihlaste.

**B. Spuštění jako správce** – pravým klikem na `start_agent.bat` →
*Spustit jako správce*. Pro automatický start pak použijte Task Scheduler
s volbou *Run with highest privileges*.

Bez oprávnění agent nespadne: ikona zčervená a upozornění ohlásí
„access denied“.

### Ovládání a autostart

Ikona v oznamovací oblasti nabízí pozastavení měření, ruční odeslání fronty,
otevření logu a ukončení. Data a logy najdete v
`%LOCALAPPDATA%\FramePulseAgent\`.

```bat
.venv\Scripts\python.exe autostart.py enable    :: start po přihlášení (HKCU Run)
.venv\Scripts\python.exe autostart.py status
.venv\Scripts\python.exe autostart.py disable
```

### Testy agenta

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.venv\Scripts\python.exe -m compileall -q framepulse_agent tests
.venv\Scripts\python.exe -m framepulse_agent --debug
```

## 3. Mobilní aplikace

```bash
cd mobile-app
cp .env.example .env.local   # Windows: copy .env.example .env.local
npm install
npx expo start
```

Do `mobile-app/.env.local` (ignorovaný gitem) vložte údaje ze svého Supabase
projektu:

```dotenv
EXPO_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon nebo publishable klíč>
```

Bez těchto hodnot použije aplikace ukázkovou adresu
`https://your-project.supabase.co` a místo dat zobrazí chybu připojení.

Naskenujte QR kód v **Expo Go** (Android/iOS). Pokud se telefon nemůže připojit
k počítači ve stejné síti, spusťte `npx expo start --tunnel`. Po každé změně
`.env.local` restartujte dev server.

### Obrazovky

- **Seznam her** – hledání, poslední průměrné FPS, datum posledního hraní,
  přidání hry, přepínač EN/CZ.
- **Detail hry** – výběr seance (den + čas), Avg / Min / Max FPS, srovnání
  s předchozí seancí a interaktivní graf z `react-native-gifted-charts`.

### Kontrola a build

```bash
npx tsc --noEmit        # typecheck
npx expo lint           # lint
npx expo-doctor         # kontrola závislostí a konfigurace
npx expo export --platform android   # ověření JS bundle bez zařízení
```

Pro instalační APK (profil `preview` v `eas.json`):

```bash
npx eas-cli@latest build --profile preview --platform android
```

## Jak vznikají metriky

1. Agent detekuje proces, který vypadá jako hra, a spustí PresentMon.
2. Framy se skládají do 2s vzorků; prvních 5 s (načítání) se ignoruje.
3. `avg_fps` = framy / měřený čas, `min_fps` = 1% low, `max_fps` = nejlepší vzorek.
4. Po ukončení hry se zapíše `sessions` a dávkově `fps_samples`.
5. Aplikace načte seznam her a vzorky vybrané seance (max. 240 bodů do grafu).

## Řešení problémů

| Příznak | Řešení |
| --- | --- |
| `Tabulky v Supabase nejsou vytvořené` (PGRST205) | spusťte `supabase_schema.sql` v SQL Editoru |
| ikona agenta zčervená, „access denied“ | chybí oprávnění PresentMonu (viz výše) |
| hra se neměří | zkontrolujte `agent.log`; malé okno nebo neznámou cestu přidejte do `force_games`; po neúspěchu platí 15minutový cooldown |
| seance se neobjevila v aplikaci | zkontrolujte `outbox/` a *Odeslat frontu* v menu agenta |
| aplikace hlásí chybu načtení | ověřte URL/klíč v `.env.local`, připojení a zda jsou tabulky vytvořené |
| Expo Go nejde připojit | stejná Wi-Fi, firewall, nebo `npx expo start --tunnel` |

## Vývojové konvence

- Grafiku v aplikaci vždy stavějte na `react-native-gifted-charts`; ruční SVG
  grafy jsou zakázané.
- Tmavé minimalistické téma (`#09090B` pozadí, `#121215` karty), čísla vždy
  s `tabular-nums`, žádné neony ani RGB dekorace.
- Agent musí běžet bez konzole a s minimální zátěží, aby nezkresloval měření.
- Podrobnosti pro práci s AI agenty jsou v [`AGENTS.md`](AGENTS.md) a
  [`mobile-app/AGENTS.md`](mobile-app/AGENTS.md).

## Licence

Projekt zatím nemá vlastní licenci. Soubor `mobile-app/LICENSE` je licencí
šablony Expo (MIT, © 650 Industries) a vztahuje se na použitou šablonu.
