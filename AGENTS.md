# AGENTS.md

Repository contains two components: `mobile-app/` (Expo app) and `pc-agent/` (Windows 11 Python agent with a system-tray icon).

## Commands

From `mobile-app/` (npm, no Bun lockfile):

```bash
npm install          # install dependencies
npx expo start       # dev server (Expo Go / QR code)
npx tsc --noEmit     # typecheck
npx expo lint        # lint
npx expo-doctor      # dependency and config checks
```

`npx expo export --platform android` verifies the native JS bundle without a device.

From `pc-agent/` (after `setup.bat` creates `.venv` and installs dependencies):

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.venv\Scripts\python.exe -m compileall -q framepulse_agent tests
.venv\Scripts\python.exe download_presentmon.py --force
.venv\Scripts\python.exe -m framepulse_agent --debug
```

`start_agent.bat` runs the agent without a console window; `setup.bat` is the one-time install (venv + dependencies + PresentMon).

## Architecture

Two decoupled components communicating through **Supabase**:

1. **`pc-agent/`** — Windows 11 headless background service (Python + PresentMon). Tracks active game name, date, Min/Avg/Max FPS, and FPS time-series data, then uploads records to Supabase.
2. **`mobile-app/`** — React Native (Expo) + TypeScript + NativeWind + `react-native-gifted-charts`. Displays telemetry synced from Supabase.

## `pc-agent` Constraints (Windows 11)

- **Headless execution:** Must run completely in the background with no console window (e.g., `pythonw` / Windows service / hidden process) and minimal CPU/GPU overhead so it does not skew frame-time measurements.
- **PresentMon permissions:** ETW capture requires either elevated **Administrator** privileges or the user account to belong to the **`Performance Log Users`** Windows group. Account for permission errors cleanly rather than failing silently.

## `mobile-app` UI & Charting Rules

- **Charting:** NEVER hand-roll raw SVG charts from scratch. Always use `react-native-gifted-charts`.
- **Visual aesthetic:** Strict minimalist dark theme inspired by Apple Health, Whoop, and Linear:
  - Background: `#09090B`
  - Card surfaces: `#121215`
  - Numeric readouts: always use `tabular-nums` (`fontVariant: ['tabular-nums']`).
  - **No gamer/AI clichés:** Avoid neon gradients, glowing borders, cyberpunk/RGB palettes, or decorative clutter.
