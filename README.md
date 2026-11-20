# FramePulse

Personal game-performance telemetry. A quiet **Windows agent** measures FPS via
[PresentMon](https://github.com/GameTechDev/PresentMon), stores gaming sessions
in **Supabase**, and a **mobile app** displays them as clean charts.

```
┌────────────────────┐   HTTPS/PostgREST   ┌────────────────────┐   HTTPS   ┌──────────────────────┐
│      pc-agent      │ ──────────────────► │      Supabase      │ ◄──────── │      mobile-app      │
│ Windows 11 + tray  │                     │ Postgres + RLS     │           │ Expo / React Native  │
│ PresentMon → FPS   │                     │ games, sessions,   │           │ game list + FPS graph│
└────────────────────┘                     │ fps_samples        │           └──────────────────────┘
                                           └────────────────────┘
```

The repository is set up for **public use**: it contains no real credentials.
Every user creates their own Supabase project and connects it following the
guide below — configuration files with real values stay on disk and git
ignores them.

## What the project can do

- **Automatic game detection** – the agent checks visible windows every 2
  seconds, ignores browsers, Discord, Steam, etc. The fact that it is a game is
  confirmed only by the frames arriving from PresentMon.
- **Non-intrusive measurement** – 2-second samples for the graph; a 5 s
  warm-up is not counted; sessions shorter than 15 s are discarded.
- **Metrics** – average FPS, **1% low** as `min_fps`, and the best 2 s sample
  as `max_fps`.
- **Offline queue** – a failed upload stays in `outbox/` and is sent later;
  writes are idempotent, so no duplicates occur.
- **Mobile overview** – list of games with search, a detail view with the
  session toggle, Avg / Min / Max FPS, and an interactive chart with a
  tooltip. Available in Czech and English.
- **Manual management** – games can be added or renamed in the app even
  without the agent.

## Repository structure

```
FPS_tracker/
├─ pc-agent/                  Windows agent (Python + PresentMon + tray)
│  ├─ framepulse_agent/       agent source code
│  ├─ tests/                  unittest suite
│  ├─ setup.bat               one-time install (venv, dependencies, PresentMon)
│  ├─ start_agent.bat         launch the agent without a console
│  ├─ start_agent.pyw         launcher for pythonw / autostart
│  ├─ autostart.py            enable/disable start on login
│  ├─ config.example.json     sample configuration
│  └─ README.md               detailed agent manual
├─ mobile-app/                Expo app (React Native + TypeScript)
│  ├─ src/app/                screens (Expo Router)
│  ├─ src/components/         cards, chart, modals, language switch
│  ├─ src/hooks/              loading data from Supabase
│  ├─ src/lib/                Supabase client, API, formatting, i18n, theme
│  └─ README.md               notes about the app
├─ supabase_schema.sql        tables, indexes, RLS policies and grants
├─ AGENTS.md                  conventions for developing with AI agents
└─ .gitignore
```

## Requirements

| Part | Needs |
| --- | --- |
| Supabase | account and project (free tier is enough) |
| pc-agent | Windows 11, Python 3.10+, PresentMon permissions |
| mobile-app | Node.js 22.13+ and npm, a phone with **Expo Go** (SDK 58) or a development build |

## 1. Supabase

1. Create a new project at [supabase.com](https://supabase.com).
2. Open the **SQL Editor**, paste the whole content of
   [`supabase_schema.sql`](supabase_schema.sql) and run it. The script is
   idempotent — you can run it repeatedly.
3. In **Project Settings → API** copy:
   - the **Project URL** in the form `https://<project-ref>.supabase.co`,
   - the **anon / publishable** key (`sb_publishable_…` or the older JWT
     `eyJ…`).

Insert these two values in two places:

| Where | Variable / key |
| --- | --- |
| `mobile-app/.env.local` | `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_ANON_KEY` |
| `pc-agent/config.json` | `supabase_url`, `supabase_key` |

> The repository contains only the sample values `https://your-project.supabase.co`
> and `your-anon-key`. Real values should never be committed.

Three tables are created:

| Table | Content |
| --- | --- |
| `games` | games by `process_name` (e.g. `Cyberpunk2077.exe`) |
| `sessions` | individual games: `played_at`, `avg_fps`, `min_fps`, `max_fps`, `duration_seconds` |
| `fps_samples` | time series: `timestamp_offset` (s) and `fps` |

> **Keys:** the publishable/anon key is public and belongs in the client – the
> data is protected by RLS policies. The `service_role` / secret key must never
> be inserted into the app or the repository. The schema deliberately allows
> the `anon` role full access because the app does not sign in. If you need
> sensitive data, enable Supabase Auth and modify the policies in
> `supabase_schema.sql`.

## 2. PC agent

The detailed manual including all configuration options is in
[`pc-agent/README.md`](pc-agent/README.md).

```bat
cd pc-agent
setup.bat            :: creates .venv, installs dependencies and downloads PresentMon
```

`setup.bat` creates `config.json` from `config.example.json` (the file is
ignored in git). **Before the first launch** replace the sample values with
yours:

```json
{
  "supabase_url": "https://<project-ref>.supabase.co",
  "supabase_key": "<anon or publishable key>"
}
```

Then start the agent:

```bat
start_agent.bat      :: launches the agent without a console window
```

Without filled-in values the agent runs, but session uploads will fail and
sessions stay in the `outbox/` queue.

### PresentMon permissions

PresentMon captures frames via ETW. Choose one of the options:

**A. `Performance Log Users` group (recommended, no UAC)** – run in a terminal
as administrator:

```bat
net localgroup "Performance Log Users" %USERNAME% /add
```

Then sign out and sign back in.

**B. Run as administrator** – right-click `start_agent.bat` → *Run as
administrator*. For autostart use a Task Scheduler job with the option
*Run with highest privileges*.

Without permissions the agent does not crash: the icon turns red and a
notification reports „access denied“.

### Control and autostart

The system tray icon offers: pause measurement, manual flush of the queue,
opening the log, and quitting. Data and logs live in
`%LOCALAPPDATA%\FramePulseAgent\`.

```bat
.venv\Scripts\python.exe autostart.py enable    :: start on login (HKCU Run)
.venv\Scripts\python.exe autostart.py status
.venv\Scripts\python.exe autostart.py disable
```

### Agent tests

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.venv\Scripts\python.exe -m compileall -q framepulse_agent tests
.venv\Scripts\python.exe -m framepulse_agent --debug
```

## 3. Mobile app

```bash
cd mobile-app
cp .env.example .env.local   # Windows: copy .env.example .env.local
npm install
npx expo start
```

Put the values from your Supabase project into `mobile-app/.env.local`
(ignored by git):

```dotenv
EXPO_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon or publishable key>
```

Without these values the app uses the sample address
`https://your-project.supabase.co` and shows a connection error.

Scan the QR code in **Expo Go** (Android/iOS). If the phone cannot connect
to the computer on the same network, run `npx expo start --tunnel`. After
every change to `.env.local`, restart the dev server.

### Screens

- **Games list** – search, last average FPS, date of the last game,
  adding games, EN/CZ switch.
- **Game detail** – session picker (day + time), Avg / Min / Max FPS,
  comparison with the previous session, and the interactive
  `react-native-gifted-charts` graph.

### Checks and build

```bash
npx tsc --noEmit        # typecheck
npx expo lint           # lint
npx expo-doctor         # dependency and config checks
npx expo export --platform android   # verifies the JS bundle without a device
```

For the distribution APK (profile `preview` in `eas.json`):

```bash
npx eas-cli@latest build --profile preview --platform android
```

## How metrics are created

1. The agent detects a process that looks like a game and starts PresentMon.
2. Frames are assembled into 2 s samples; the first 5 s (loading) are
   ignored.
3. `avg_fps` = frames / measured time, `min_fps` = 1% low, `max_fps` =
   best sample.
4. When the game ends, a row is written to `sessions` and the samples are
   uploaded to `fps_samples` in batches.
5. The app loads the game list and the samples of the selected session
   (max. 240 points in the chart).

## Troubleshooting

| Symptom | Solution |
| --- | --- |
| `The Supabase tables are not created` (PGRST205) | run `supabase_schema.sql` in the SQL Editor |
| agent icon red, „access denied“ | missing PresentMon permissions (see above) |
| game is not being measured | check `agent.log`; add the small window or unknown path to `force_games`; after a failure a 15-minute cooldown applies |
| the session did not appear in the app | check `outbox/` and the *Send queue* in the agent menu |
| the app reports a loading error | verify URL/key in `.env.local`, the connection, and that the tables are created |
| Expo Go will not connect | same Wi-Fi, firewall, or `npx expo start --tunnel` |

## Development conventions

- In-app graphics must always be built on `react-native-gifted-charts`;
  hand-rolled SVG graphs are forbidden.
- Minimalist dark theme (`#09090B` background, `#121215` cards), numbers
  always use `tabular-nums`, no neon or RGB decorations.
- The agent must run without a console and with minimal load so it does not
  skew measurements.
- Details for working with AI agents are in [`AGENTS.md`](AGENTS.md) and
  [`mobile-app/AGENTS.md`](mobile-app/AGENTS.md).

## License

This project is published under the **MIT License**. The full license text is
in the [`LICENSE`](LICENSE) file at the root of the repository.

The Expo template used by the mobile app carries its own MIT license in
[`mobile-app/LICENSE`](mobile-app/LICENSE) (© 650 Industries).
