# Server Monitor architecture

## Overview

A ready-to-run folder for Windows. Map server names to SSH aliases in
`servers.json`, set shared settings and `LANGUAGE=ru|en` in `.env`, double-click
`start.cmd`, and see live CPU, RAM, swap, disk and processes for several Linux servers.
The SSH user may be root or a normal user. Do not install software, services
or files on the remote server.

## Architecture and constraints

- Local Python 3.11+ standard library server, native OpenSSH, plain HTML/CSS/JS.
- Windows 10/11 with OpenSSH; start script finds or bootstraps local Python.
- Existing SSH config is authoritative: aliases, ports, identities, ProxyJump.
- Remote Linux sampler uses `sh`, `awk`, `cat`, `df`, `uname`, procfs. No sudo.
- One persistent SSH session per configured server; all collect from startup.
  Authentication uses a shared cancellable lock until the first valid frame,
  keeping console prompts separate while connected sessions run independently.
  Each server owns a state, one-hour history, reconnect path and numbered SSH log.
  A shared shutdown event cancels queued authentication before stopping and
  joining the individual collectors. Spawned SSH processes remain inside their
  cleanup scope even if starting a reader/writer thread fails.
- Listen only on 127.0.0.1, port 8765 by default. Token-gated JSON API, strict
  Host/Origin checks, fixed public static routes, no shell-command HTTP API.
- CPU measured from counter deltas, guest counters not double-counted;
  RAM from MemAvailable; no swap is explicitly disabled, not a failed metric.
- Disk defaults to `/`; percentage uses df semantics (used / used+available).
- Keep up to one hour of history in RAM. No collection when the app is closed.
- Explicit demo mode for inspecting UI. Real mode never invents metric values.
- Status reflects startup, authentication, connected, reconnecting and stale.
  Three consecutive sessions without a valid sample stop automatic attempts
  with status `error`; manual reconnect resets the counter. A session with
  valid data resets it too. Waiting after the limit remains cancellable.
  Connected servers appear first in the sidebar, then connecting servers,
  then unavailable servers; selection and server IDs do not change.
- Compact UI: collapsible server sidebar, RU/EN selector, four metric cards,
  smaller selected history chart, top five processes, server facts and optional
  seven-day traffic. Keep 5/15/60-minute windows, pause/resume and reconnect.
  Desktop viewport targets are 1280x720 and 1366x768 with no document scrolling;
  narrow mobile screens may scroll. Language and sidebar preferences are local
  to the browser. Default language is injected into HTML and returned by API.
- Optional `ps` provides PID, command name, RSS bytes and average lifetime CPU;
  one process listing yields the union of the top five by CPU and top five
  by RSS (at most ten records). Clickable CPU/RAM headers select the five
  highest consumers for that metric in descending order.
  command arguments are not collected. This CPU may exceed 100% and is labelled
  as an average, not an interval measurement. Missing/unsupported `ps` is null.
- Optional vnStat JSON API v2 (`vnstat --json d 7`) is read about once a minute,
  with bounded execution, payload and interface count. Counters are bytes.
  Seven calendar dates end at server today; missing readings remain null.
  Select one interface, preferring the default route; never sum interfaces.
  Missing/unsupported/unreadable statistics hide the entire block. No remote
  installation, daemon changes or writes are performed.
  The traffic picker is a keyboard-accessible custom listbox. Clicking a day
  exposes RX, TX and their sum; missing counters remain unknown. Totals at or
  above 1 GiB use GiB even above 1 TiB, matching daily report comparisons.
  RU/EN is a single toggle button. The redundant timezone/history footer text
  is omitted; the last-update timestamp remains visible.
- Optional `vcgencmd measure_temp` supplies Raspberry Pi CPU temperature in
  Celsius on each cycle, using the existing collector and a bounded command.
  Missing, failed or malformed readings are null and hide the separate
  temperature card below Server details. Windows and demo sources return null.
- Optional process/traffic details belong only to `latest`; history keeps
  graph metrics and host facts, avoiding repeated seven-day payloads in RAM.

## Configuration

`servers.json` is a UTF-8/BOM object such as
`{"Production":"production","Backup":{"alias":"backup","jump":"gateway"}}`.
Accept 1–32 unique names and routes (alias plus optional jump), names up to 80 characters without controls, aliases matching
`[A-Za-z0-9][A-Za-z0-9_.@:+-]{0,252}`. Reject duplicate JSON keys, duplicate
routes, malformed JSON and files larger than 64 KiB. Object entries accept only
`alias` and optional `jump`; both use the alias validation. `jump` supplies one
OpenSSH `-J` alias. Without it, the user's ProxyJump remains authoritative.
Never interpret names
or aliases as shell syntax. Entries receive opaque string IDs in file order
(`"0"`, `"1"`, ...); HTTP accepts only these configured IDs.

`.env` has eight recognized options: `PORT`, `INTERVAL`, `DISK_PATH`,
`SSH_BATCH_MODE`, `SSH_CONFIG`, `LANGUAGE`, `MONITOR_SELF`, `WSL_AUTODETECT`.
Both booleans default to false. Existing validation and environment
precedence remain. A legacy `SSH_ALIAS` entry gives a migration message.
Python CLI supports `--servers`; the Windows launcher uses the default filename.
Explicit `--demo` uses three synthetic servers and requires no SSH or JSON file.

### Optional local sources

- `MONITOR_SELF` adds ID/name `self` for the machine running Python, with OS
  auto-detection. Windows uses stdlib ctypes Windows APIs; Linux reuses the
  procfs probe. Other platforms report an unsupported-source error.
- `WSL_AUTODETECT` enumerates only running Windows WSL distributions once at
  startup, adding IDs `wsl-0`, `wsl-1`, etc. It does not rewrite configuration.
  Before reconnect, verify that the distribution is still running. Never use
  WSL shutdown/terminate to stop a collector: clean up only its process group.
  Linux local/WSL probes require `setsid` for owned process-group cleanup.
- Empty SSH mapping `{}` is allowed if either local option is enabled. Fail
  clearly if discovery leaves no configured sources. SSH discovery is required
  only when SSH entries exist; demo ignores both local flags.
- Windows CPU uses counter deltas; RAM is physical available memory; swap is
  actual pagefile usage, not commit. Disk is the Windows system drive, while
  `DISK_PATH` applies to Linux and WSL. Process CPU remains lifetime average;
  inaccessible metrics are null. Windows load/iowait/steal/traffic are null.
- History, pause, access controls and per-source reconnect remain shared.
  Snapshots and each `/api/servers` entry include `source: "ssh"|"self"|"wsl"`.
  Existing numeric SSH IDs stay unchanged; HTTP treats all IDs as opaque.
  The frontend labels local sources SELF/WSL and avoids SSH-only status text.

## Shared Python interface

`monitor.metrics.build_probe(interval: int, disk_path: str) -> str`
returns the full remote shell script. Frames are delimited by the exact lines
`__SM_BEGIN__` and `__SM_END__`. `parse_frame(text: str) -> dict` parses the
contents (including or excluding marker lines). `MetricCalculator().update(raw,
timestamp: float | None = None) -> dict` returns the sample below. Reset the
calculator on reconnect. `timestamp` is the local receive time as Unix seconds;
returned `ts` is Unix milliseconds. Null represents missing data, not zero.

## Shared JSON interface

Every `/api/` route requires `X-Monitor-Token`, injected into the HTML meta tag
`monitor-token` at render time using placeholder `__MONITOR_TOKEN__`.
The meta tag `monitor-language` receives `__MONITOR_LANGUAGE__` as `ru` or `en`.

API messages and diagnostics are English. The frontend localizes messages
when `ru` is selected. Documentation and static HTML fallback text are English.

`GET /api/servers` returns:

```json
{
  "language": "ru",
  "default_server": "0",
  "servers": [
    {"id": "0", "name": "Production", "alias": "my-server", "source": "ssh", "status": "connecting", "demo": false}
  ]
}
```

`GET /api/snapshot?server=0` returns the selected cache plus `server_id`, `name`,
`language`, `default_server` and the same lightweight `servers` list. Omitting
`server` selects `"0"`; invalid/unknown/duplicate IDs are rejected. Example state:

```json
{
  "status": "connected",
  "message": "Connected through SSH",
  "alias": "my-server",
  "source": "ssh",
  "interval": 2,
  "demo": false,
  "server_time": 1791398000000,
  "last_update": 1791398000000,
  "connected_since": 1791397980000,
  "history": [],
  "latest": {
    "ts": 1791398000000,
    "cpu": {"percent": 40.3, "cores": 2, "mhz": 2590, "model": "CPU", "iowait": 0.1, "steal": 0.0, "temperature_c": null},
    "memory": {"percent": 65.1, "used": 1342177280, "total": 2147483648, "available": 805306368},
    "swap": {"percent": 28.9, "used": 620756992, "total": 2147483648, "enabled": true},
    "disk": {"percent": 73.7, "used": 19402514759, "total": 26338836480, "available": 6936325324, "path": "/", "device": "/dev/vda1"},
    "host": {"hostname": "server", "os": "Ubuntu", "kernel": "6.8.0", "arch": "x86_64", "uptime": 86400, "load": [0.4,0.3,0.2]},
    "processes": [{"pid": 42, "name": "python3", "cpu_percent": 125.4, "memory_bytes": 134217728}],
    "traffic": null
  }
}
```

`traffic`, when available, has `updated_at` (local read milliseconds),
`default_interface`, and `interfaces`. Each interface has `name`, `rx` and `tx`
totals for known days (null if no known values), and exactly seven ascending
`days` with `date` (YYYY-MM-DD), `rx`, `tx` in bytes or null. A real measured zero
is preserved. Refresh failure clears traffic; no new read keeps the cached value.

`history` contains graph/host samples ordered ascending, excluding `processes`
and `traffic`. Reconnection preserves history and resets CPU delta calculation.
Statuses are `connecting`, `connected`, `reconnecting`, `error`, `stopped`.
`POST /api/reconnect?server=0` requests reconnect of that server only, returns
`{"ok":true}`. UI polls every interval without overlapping requests; paused
view leaves all collection running. Different tabs can select different servers.
Frontend renders all received strings as text and discards outdated selections.

## Acceptance checks

- Unit tests independently compute CPU, memory, swap and filesystem metrics.
- Run the real shell probe locally and over an isolated local SSH daemon.
- Test normal unprivileged SSH, successful sampling, disconnect and recovery.
- Check API token, Host and Origin validation, configuration injection inputs,
  missing files, API error handling, bounded history and stale data.
- Inspect actual desktop and mobile rendering.
- Verify server switching, independent history/reconnect, queued authentication,
  RU/EN static/dynamic labels, top processes and absent-traffic layout.
- Verify controls and absence of JS errors in a real browser.
- Compile Python, syntax-check JS and PowerShell where runtime is available.
- Inspect final ZIP: relative safe paths, .env and AGENTS.md present, no keys,
  logs, runtime cache, temporary test data, or development dependencies.
- Windows execution cannot be claimed unless a Windows host actually ran it.
