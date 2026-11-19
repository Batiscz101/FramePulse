# FramePulse PC agent

Tichý Windows agent, který pozná spuštěnou hru, změří FPS přes **PresentMon** a po
ukončení hry uloží seanci do **Supabase** (tabulky `games`, `sessions`,
`fps_samples`). Běží bez konzolového okna, ovládá se ikonou v oznamovací oblasti.

## Jak to funguje

- Každé 2 sekundy zkontroluje viditelná okna. Za hru považuje proces, který není
  v seznamu ignorovaných aplikací (prohlížeče, Explorer, Discord, Steam…), a
  buď je už známý z databáze, má okno přes většinu obrazovky, nebo leží
  v typické herní složce (Steam, Epic, GOG, Xbox…).
- Skutečnost, že jde o hru, potvrdí až PresentMon – pokud do 90 sekund nepřijde
  ani jeden frame, proces se na 15 minut zablokuje a nic se neukládá.
- Ze zachycených frame times skládá **2sekundové vzorky** pro graf. Prvních
  5 sekund (načítání hry) se do metrik nezapočítává.
- `avg_fps` = framy / měřený čas, `min_fps` = **1% low** (průměr nejhoršího 1 %
  frame times), `max_fps` = nejlepší 2s vzorek.
- Seance kratší než **15 sekund** (celková doba včetně načítání) se zahazuje.
  Po ukončení hry se zapíše řádek do `sessions` a vzorky se nahrají dávkově do
  `fps_samples`.
- Když je PC offline nebo Supabase neodpovídá, seance zůstane ve frontě
  (`outbox/`) a odešle se později. Zápis je idempotentní (předem vygenerovaná
  UUID seance a před vložením vzorků se mažou staré řádky), takže opakovaný
  upload nevytvoří duplikáty.
- Hru najde nebo založí v `games` podle `process_name` (`cyberpunk2077.exe`).
  Název se odvodí z `.exe` a titulku okna (`Cyberpunk2077.exe` → `Cyberpunk 2077`).

## Požadavky

- Windows 11, Python 3.10+ (testováno na 3.14).
- Spuštěné [`supabase_schema.sql`](../supabase_schema.sql) v Supabase projektu.
- Oprávnění pro PresentMon (viz níže).

## Instalace

1. Dvojklikem spusťte **`setup.bat`**. Vytvoří `.venv`, nainstaluje závislosti,
   stáhne oficiální PresentMon do `tools/PresentMon.exe` a založí `config.json`.
2. (Volitelně) upravte `config.json` – výchozí hodnoty stačí.
3. Spusťte **`start_agent.bat`**. V oznamovací oblasti se objeví ikona pulzu.

Agent se sám drží v jednom exempláři – druhé spuštění jen upozorní, že už běží.

## Oprávnění PresentMonu

PresentMon zachytává framy přes ETW a potřebuje jedno z těchto:

**A. Skupina `Performance Log Users` (doporučeno, bez UAC)**

V terminálu **spuštěném jako správce**:

```bat
net localgroup "Performance Log Users" %USERNAME% /add
```

Potom se **odhlaste a znovu přihlaste** (změna skupin se projeví až při novém
přihlášení). Ověření:

```bat
whoami /groups | findstr /i "Performance Log Users"
```

**B. Spuštění agenta jako správce**

Klikněte pravým na `start_agent.bat` → *Spustit jako správce*. Autostart přes
registr v tomto případě nestačí (UAC by ho nespustil se zvýšenými právy); řešením
je naplánovaná úloha v Task Scheduleru s volbou *Run with highest privileges*.

Bez oprávnění agent nespadne – ikona zčervená a přijde upozornění
„PresentMon nemá oprávnění (access denied)“. Hra se pak 15 minut neměří, aby
nevznikala smyčka chyb.

## Ovládání

Kliknutí na ikonu otevře menu:

| Položka | Význam |
| --- | --- |
| *(první řádek)* | stav: čekání / měřená hra s aktuálním FPS / pozastaveno / chyba |
| Pozastavit měření | přestane detekovat hry; rozpracovaná seance se uloží |
| Odeslat frontu (N) | zkusí odeslat seance čekající v `outbox/` |
| Otevřít log | otevře `agent.log` |
| Otevřít složku s daty | otevře `%LOCALAPPDATA%\FramePulseAgent` |
| Ukončit FramePulse | zastaví agenta; rozdělaná seance se uloží do fronty |

Tooltip ikony ukazuje stav a u měřené hry i živé FPS.

## Automatické spuštění po přihlášení

```bat
.venv\Scripts\python.exe autostart.py enable
.venv\Scripts\python.exe autostart.py status
.venv\Scripts\python.exe autostart.py disable
```

Zapisuje do `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` hodnotu
`FramePulseAgent`, která spouští `start_agent.pyw` přes `pythonw.exe` s parametrem
`--silent` (žádná chybová okna při přihlášení). Nevyžaduje správce.

Alternativa: zástupce na `start_agent.pyw` vložte do složky
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

## Konfigurace (`config.json`)

Soubor se vytvoří při prvním spuštění (nebo ho zkopíruje `setup.bat`
z `config.example.json`). Změny se projeví po restartu agenta.

| Klíč | Výchozí | Význam |
| --- | --- | --- |
| `supabase_url` | projektová URL | `https://<ref>.supabase.co` |
| `supabase_key` | publishable klíč | veřejný klíč, data chrání RLS |
| `presentmon_path` | `tools/PresentMon.exe` | cesta k PresentMonu (relativně k `pc-agent/`) |
| `poll_interval_seconds` | `2.0` | jak často kontrolovat okna |
| `sample_interval_seconds` | `2.0` | délka jednoho bodu grafu |
| `min_session_seconds` | `15` | kratší hraní se neukládá |
| `warmup_seconds` | `5.0` | načítání na začátku se nezapočítává |
| `confirm_frames_seconds` | `90` | bez framů za tuto dobu proces není hra |
| `stall_seconds` | `600` | po tak dlouhé pauze ve framech se seance uzavře |
| `no_game_cooldown_seconds` | `900` | jak dlouho se neúspěšný proces ignoruje |
| `preflight_on_start` | `true` | ověřit PresentMon hned při startu |
| `notifications` | `true` | balónková oznámení |
| `notify_on_upload` | `false` | oznámení i po každém úspěšném uploadu |
| `upload_chunk_size` | `500` | po kolika vzorcích se posílá `fps_samples` |
| `request_timeout_seconds` | `20` | timeout HTTP požadavku |
| `ignore_processes` | `[]` | další procesy, které se nemají měřit (`"app.exe"`) |
| `force_games` | `[]` | procesy, které se mají měřit i v malém okně |
| `data_dir` | `""` | prázdné = `%LOCALAPPDATA%\FramePulseAgent` |
| `debug` | `false` | podrobný log |

Tip: hra, která běží v malém okně a nemá typickou herní cestu, se nemusí
detekovat. Přidejte její `.exe` do `force_games`.

## Data a logy

`%LOCALAPPDATA%\FramePulseAgent\`

- `logs\agent.log` – rotující log (1 MB × 3 zálohy), `fatal.log` při pádu před
  nastavením logování,
- `outbox\` – seance čekající na odeslání (JSON, mažou se po úspěšném uploadu),
- `captures\` – rezervováno pro budoucí diagnostiku.

Do databáze se zapisuje:

- `games` – jedna hra na `process_name`, název v `name`,
- `sessions` – `played_at` (UTC), `avg_fps`, `min_fps`, `max_fps`,
  `duration_seconds`,
- `fps_samples` – `timestamp_offset` v sekundách od začátku měření a `fps`.

## Řešení problémů

| Příznak | Řešení |
| --- | --- |
| `Tabulky v Supabase nejsou vytvořené` (PGRST205) | spusťte `supabase_schema.sql` v SQL Editoru |
| ikona zčervená, „access denied“ | chybí oprávnění PresentMonu (viz výše) |
| ikona se neobjeví | zkontrolujte `logs\agent.log`; spusťte `setup.bat`, pokud chybí závislosti |
| hra se neměří | podívejte se do logu na „Detekována hra“; případně přidejte `.exe` do `force_games`; po neúspěchu platí 15minutový cooldown |
| seance se neobjevila v aplikaci | zkontrolujte `outbox/` a tlačítko *Odeslat frontu*; log obsahuje důvod chyby |
| antivirus se ptá na `pythonw.exe` | povolte ho, agent potřebuje pouze čtení oken a síť |

## Vývoj a testy

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.venv\Scripts\python.exe -m compileall -q framepulse_agent tests
.venv\Scripts\python.exe download_presentmon.py --force
.venv\Scripts\python.exe -m framepulse_agent --debug
```

Poslední příkaz spustí agenta s logem do konzole (užitečné při ladění detekce).
`--silent` potlačí chybová okna, `--config cesta.json` použije jinou konfiguraci.

Struktura:

```
pc-agent/
├─ framepulse_agent/
│  ├─ app.py            vstupní bod (config, logging, tray)
│  ├─ monitor.py        stavový automat detekce a měření
│  ├─ tray.py           ikona a menu (pystray)
│  ├─ capture.py        PresentMon + parser CSV
│  ├─ detection.py      enumerace oken a heuristika her
│  ├─ naming.py         názvy her z .exe a titulku
│  ├─ metrics.py        vzorky, průměr, 1% low
│  ├─ upload.py         sestavení seance, outbox, dávkový upload
│  ├─ supabase.py       tenký PostgREST klient
│  ├─ config.py         načtení config.json
│  └─ …
├─ tests/               unittest sada
├─ tools/PresentMon.exe stáhne setup.bat / download_presentmon.py
├─ setup.bat            jednorázová instalace
├─ start_agent.bat      spuštění bez konzole
├─ start_agent.pyw      spouštěč pro pythonw / autostart
├─ autostart.py         HKCU Run enable/disable/status
└─ config.json          vznikne při prvním spuštění
```

## Poznámky

- Agent sám sebe neelevuje (žádné UAC) – oprávnění se řeší skupinou nebo
  ručním spuštěním jako správce.
- PresentMon se spouští skrytě (`CREATE_NO_WINDOW`) a jeho výstup se čte po
  řádcích, takže agent nekonzumuje prakticky žádné CPU navíc.
- Podporován je PresentMon **2.x** (výstup `--output_stdout`); sloupce CSV se
  hledají podle hlavičky, takže funguje i s jiným pořadím sloupců.
