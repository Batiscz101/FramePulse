# FramePulse PC agent

A quiet Windows agent that recognizes the running game, measures FPS via
**PresentMon** and saves the session to **Supabase** (tables `games`,
`sessions`, `fps_samples`) when the game ends. Runs without a console window;
controlled via the icon in the system tray.

## How it works

- Every 2 seconds it checks visible windows. A process is treated as a game if
  it is not in the ignore list (browsers, Explorer, Discord, Steam, …), is
  either already known from the database, has a window covering most of the
  screen, or lies in a typical game folder (Steam, Epic, GOG, Xbox…).
- The fact that it is a game is confirmed by PresentMon — if no frame arrives
  within 90 seconds, the process is blocked for 15 minutes and nothing is
  saved.
- Captured frame times are assembled into **2-second samples** for the graph;
  the first 5 seconds (loading) are excluded from the metrics.
- `avg_fps` = frames / measured time, `min_fps` = **1% low** (average of the
  worst 1 % of frame times), `max_fps` = best 2 s sample.
- Sessions shorter than **15 seconds** (including loading time) are discarded.
  When the game ends, a row is written to `sessions` and the samples are
  uploaded to `fps_samples` in batches.
- If the PC is offline or Supabase does not respond, the session stays in the
  queue (`outbox/`) and is sent later. Writes are idempotent (the session UUID
  is pre-generated, and old rows are deleted before inserting samples), so
  repeated uploads never create duplicates.
- The game is found or created in `games` by `process_name`
  (`cyberpunk2077.exe`). The name is derived from the `.exe` and the window
  title (`Cyberpunk2077.exe` → `Cyberpunk 2077`).

## Requirements

- **Windows 10 version 1809/1903 or newer, or Windows 11 – 64-bit only.**
- Python 3.10+ for running from source (tested on 3.14). The standalone exe
  does not need Python.
- `supabase_schema.sql` running in the Supabase project.
- PresentMon permissions (see below).
- Microsoft Visual C++ Redistributable 2015–2022 (x64), which PresentMon needs.
  It is already present on most PCs; if it is missing, the agent shows an
  English notification with the fix.

## Windows compatibility

- The agent uses only Python, `psutil` and the Win32 API through `ctypes`. It
  never calls PowerShell, Windows 11-only commands or PowerShell 7+ features,
  so Windows PowerShell 5.1 (or no PowerShell at all) is sufficient.
- Game detection uses `EnumWindows`, `GetWindowRect`, `MonitorFromWindow` and
  `psutil`, all available on Windows 10 1809/1903 and Windows 11.
- PresentMon needs ETW permissions. Without them you get a clear English
  notification (administrator or the `Performance Log Users` group).

## Installation

1. Double-click **`setup.bat`**. It creates `.venv`, installs dependencies,
   downloads the official PresentMon to `tools/PresentMon.exe` and creates
   `config.json`.
2. Edit `config.json` and fill in `supabase_url` and `supabase_key` from your
   Supabase project (Project Settings → API).
3. Start **`start_agent.bat`**. A pulse icon appears in the tray.

The agent keeps a single instance – another launch only warns that it is
already running.

## Building the standalone executable (Windows)

```bat
cd pc-agent
setup.bat        :: one-time: venv, dependencies, PresentMon download
build_exe.bat    :: builds dist\FramePulseAgent.exe
```

- `dist\FramePulseAgent.exe` – a clean single-file build
  (`--noconsole --onefile --name FramePulseAgent`) with the FramePulse icon,
  PresentMon and `config.example.json` bundled inside.
- Run it directly – the tray agent starts without a console. `config.json` is
  looked up **next to the executable** first, then in
  `%LOCALAPPDATA%\FramePulseAgent\`. If neither exists, it is created next to
  the exe (or in `%LOCALAPPDATA%` when the exe folder is read-only) from the
  bundled example. The temporary PyInstaller `_MEIPASS` folder is never used
  for the configuration.
- PresentMon is bundled inside the exe. A copy next to the exe
  (`PresentMon.exe` or `tools\PresentMon.exe`) or in
  `%LOCALAPPDATA%\FramePulseAgent\` takes precedence; if none is found, the
  agent downloads it to `%LOCALAPPDATA%\FramePulseAgent\tools\PresentMon.exe`.
- Autostart: run from a terminal so the confirmation is visible:

  ```bat
  dist\FramePulseAgent.exe --autostart enable
  dist\FramePulseAgent.exe --autostart status
  dist\FramePulseAgent.exe --autostart disable
  ```

  `enable` writes the full path to `FramePulseAgent.exe` into
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`; `status` and `disable`
  show or remove it.

## PresentMon permissions

PresentMon captures frames via ETW and needs one of:

**A. `Performance Log Users` group (recommended, no UAC)**

In a terminal **run as administrator**:

```bat
net localgroup "Performance Log Users" %USERNAME% /add
```

Then **sign out and sign back in** (group changes take effect on the next
login). Verification:

```bat
whoami /groups | findstr /i "Performance Log Users"
```

**B. Running the agent as administrator**

Right-click `start_agent.bat` → *Run as administrator*. In this case
autostart via the registry is not enough (UAC would not start it with
elevated rights); the fix is a scheduled task in Task Scheduler with the
option *Run with highest privileges*.

Without permissions the agent does not crash – the icon turns red and a
notification reports „PresentMon does not have permission (access denied)“. The game
then stays unmeasured for 15 minutes so that a loop of errors does not occur.

## Controls

Clicking the icon opens the menu:

| Entry | Meaning |
| --- | --- |
| *(first row)* | status: waiting / game being measured with live FPS / paused / error |
| Pause measuring | stops detecting games; a partial session is saved |
| Send queue (N) | tries to send the sessions waiting in `outbox/` |
| Open log | opens `agent.log` |
| Open data folder | opens `%LOCALAPPDATA%\FramePulseAgent` |
| Quit FramePulse | stops the agent; a partial session is saved to the queue |

The icon tooltip shows the status, and for a measured game the live FPS too.

## Autostart on login

```bat
.venv\Scripts\python.exe autostart.py enable
.venv\Scripts\python.exe autostart.py status
.venv\Scripts\python.exe autostart.py disable
```

It writes the value `FramePulseAgent` to
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, which starts
`start_agent.pyw` via `pythonw.exe` with the `--silent` parameter (no error
windows on login). No administrator is required.

For the standalone executable use the built-in switch instead – it stores the
path to the exe itself:

```bat
dist\FramePulseAgent.exe --autostart enable
```

Alternative: put a shortcut to `start_agent.pyw` (or to
`FramePulseAgent.exe`) in the folder
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

## Configuration (`config.json`)

The file is created on first launch (or copied from `config.example.json`).
Changes take effect after restarting the agent. When running from source it
lives in `pc-agent/`; the standalone `FramePulseAgent.exe` looks next to itself
first and then in `%LOCALAPPDATA%\FramePulseAgent\`.

| Key | Default | Meaning |
| --- | --- | --- |
| `supabase_url` | project URL | `https://<ref>.supabase.co` |
| `supabase_key` | publishable key | public key; data is protected by RLS |
| `presentmon_path` | `tools/PresentMon.exe` | path to PresentMon (relative to the agent/exe folder) |
| `poll_interval_seconds` | `2.0` | how often visible windows are checked |
| `sample_interval_seconds` | `2.0` | length of one graph point |
| `min_session_seconds` | `15` | shorter sessions are not saved |
| `warmup_seconds` | `5.0` | loading at the start is not counted |
| `confirm_frames_seconds` | `90` | without frames for this long a process is not a game |
| `stall_seconds` | `600` | after this long a pause in frames the session is closed |
| `no_game_cooldown_seconds` | `900` | how long a failed process is ignored |
| `preflight_on_start` | `true` | verify PresentMon on startup |
| `notifications` | `true` | balloon notifications |
| `notify_on_upload` | `false` | notify on every successful upload |
| `upload_chunk_size` | `500` | how many samples are sent with `fps_samples` |
| `request_timeout_seconds` | `20` | HTTP request timeout |
| `ignore_processes` | `[]` | additional processes not to measure (`"app.exe"`) |
| `force_games` | `[]` | processes to measure even in a small window |
| `data_dir` | `""` | empty = `%LOCALAPPDATA%\FramePulseAgent` |
| `debug` | `false` | detailed log |

Tip: if a game runs in a small window and has no typical game path, it may
need to be added to `force_games`.

## Data and logs

`%LOCALAPPDATA%\FramePulseAgent\`

- `logs\agent.log` – rotating log (1 MB × 3 backups), `fatal.log` on a crash
  before logging is set up,
- `outbox\` – sessions waiting to be sent (JSON, deleted after successful
  upload),
- `captures\` – reserved for future diagnostics.

The database receives:

- `games` – one game per `process_name`, name in `name`,
- `sessions` – `played_at` (UTC), `avg_fps`, `min_fps`, `max_fps`,
  `duration_seconds`,
- `fps_samples` – `timestamp_offset` in seconds since the start of the
  measurement and `fps`.

## Troubleshooting

| Symptom | Solution |
| --- | --- |
| `The Supabase tables are not created` (PGRST205) | run `supabase_schema.sql` in the SQL Editor |
| icon red, „access denied“ | missing PresentMon permissions (see above); applies to Windows 10 and 11 |
| `VCRUNTIME140.dll was not found` / `Visual C++` notification | install the x64 Microsoft Visual C++ Redistributable 2015–2022, then restart the agent |
| icon does not appear | check `logs\agent.log`; run `setup.bat` if dependencies are missing |
| game is not measured | look for „Game detected“ in the log; optionally add the `.exe` to `force_games`; after a failure the 15-minute cooldown applies |
| the session did not appear in the app | check `outbox/` and the *Send queue* button; the log contains the reason for the error |
| antivirus asks about `pythonw.exe` / `FramePulseAgent.exe` | allow it; the agent needs only window reading and network access |
| the exe starts but does not upload | check `logs\agent.log`; `config.json` next to the exe still has the sample Supabase values |
| the exe does not create `config.json` | the exe folder is read-only; the file is then created in `%LOCALAPPDATA%\FramePulseAgent\` |

## Development and tests

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.venv\Scripts\python.exe -m compileall -q framepulse_agent tests
.venv\Scripts\python.exe download_presentmon.py --force
.venv\Scripts\python.exe -m framepulse_agent --debug
```

The last command starts the agent with logging in the console (useful for
detection debugging). `--silent` suppresses error windows, `--config path`
uses a different configuration.

Structure:

```
pc-agent/
├─ framepulse_agent/
│  ├─ app.py            entry point (config, logging, tray)
│  ├─ monitor.py        state machine for detection and measurement
│  ├─ tray.py           icon and menu (pystray)
│  ├─ capture.py        PresentMon + CSV parser
│  ├─ detection.py      window enumeration and game heuristics
│  ├─ naming.py         game names from .exe and window title
│  ├─ metrics.py        samples, average, 1% low
│  ├─ upload.py         session assembly, outbox, batched upload
│  ├─ supabase.py       thin PostgREST client
│  ├─ config.py         reading config.json
│  └─ …
├─ tests/               unittest suite
├─ tools/PresentMon.exe downloaded by setup.bat / download_presentmon.py
├─ assets/              application icon (framepulse.ico) + generator
├─ build_exe.bat        builds dist\FramePulseAgent.exe (PyInstaller)
├─ setup.bat            one-time install
├─ start_agent.bat      start without console
├─ start_agent.pyw      launcher for pythonw / autostart
├─ autostart.py         HKCU Run enable/disable/status
├─ config.json          created on first launch (ignored by git)
└─ dist/                build output, ignored by git
```

## Notes

- The agent does not elevate itself (no UAC) – permissions are resolved
  either via the group or manual admin launch.
- PresentMon runs hidden (`CREATE_NO_WINDOW`) and its output is read line by
  line, so the agent consumes practically no extra CPU.
- PresentMon **2.x** is supported (`--output_stdout` output); the CSV
  columns are searched by header, so it also works if the order differs.
