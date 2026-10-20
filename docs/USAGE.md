# User guide

For first-time setup, see the [quick start](../README.md#quick-start).

## Requirements

- Windows 10 or 11 and Windows PowerShell 5.1. Windows OpenSSH Client is required only for SSH sources.
- An existing OpenSSH connection. Settings normally live in `%USERPROFILE%\.ssh\config`. The application uses your `User`, keys, `Port`, `ProxyJump` and other applicable SSH options.
- Remote Linux with `/proc` and standard `sh`, `awk`, `cat`, `df` and `uname` commands. The SSH account can be a regular user or `root`; collecting metrics requires no elevated privileges.

The launcher uses an existing Python 3.11+ installation or the official embeddable Python 3.14.8 under `.runtime` next to the application. Python dependencies are all in the standard library; there are no `pip` or `npm` commands. The local runtime is prepared without an installer. Remote commands only read data, without installing packages, services or files.

`start.cmd` sets the PowerShell execution policy for its own process only. System settings and the persistent `PATH` are preserved. If a corporate policy blocks execution, contact your administrator or run `python server.py` with an approved Python installation.

## Settings

| Name | Default | Meaning |
| --- | --- | --- |
| `LANGUAGE` | `ru` | Initial dashboard language: `ru` or `en`. The toggle is at the top right. The browser saves its selection, which takes precedence over this setting. |
| `PORT` | `8765` | Dashboard port on `127.0.0.1`. |
| `INTERVAL` | `2` | Collection interval from 1 to 60 seconds. |
| `DISK_PATH` | `/` | Absolute Linux path on the filesystem to monitor, such as `/srv`. |
| `SSH_BATCH_MODE` | `false` | Allow normal interactive SSH prompts. Use `true` for an already configured key/agent login to a known host. |
| `SSH_CONFIG` | empty | Optional path to a separate SSH config. An empty value uses the normal user configuration. |
| `MONITOR_SELF` | `false` | Show `SELF`: the computer running the monitor. Its OS is detected automatically; Windows and Linux are supported. |
| `WSL_AUTODETECT` | `false` | On Windows, detect already running WSL distributions at startup and add them to the menu. |

Example of a separate SSH config:

```dotenv
SSH_CONFIG="C:\Users\Alex\.ssh\work config"
```

`.env` supports UTF-8 with or without a BOM, whole-line comments and simply quoted values. Backslashes in Windows paths remain literal. Relative `SSH_CONFIG` paths are resolved from the application folder. Environment variables with the same names override `.env`. `servers.json` is UTF-8 JSON without comments, with up to 32 SSH servers and names up to 80 characters. Names and routes (alias plus jump) must be unique. An empty object is allowed when local sources are enabled. An alias contains only an SSH connection name, without the `ssh` command or arguments. Restart the application after changing either file. When launching through Python, you can select different files: `python server.py --env settings.env --servers hosts.json --check`.

### SSH through a jump host (`-J`)

The original string format remains supported. A server can also specify `jump`, another `Host` alias from the same OpenSSH config:

```json
{
  "Production": {"alias": "private-server", "jump": "gateway"},
  "Backup": "backup"
}
```

The monitor passes `-J gateway` to native OpenSSH. Without `jump`, `ProxyJump` from the SSH config applies. Configure ports, users and keys for both hosts in the SSH config; normal host key verification remains enabled. The `jump` field accepts one alias. Use `ProxyJump` in the SSH config for a chain of hosts. The same destination alias may use different jump aliases; duplicate routes are rejected.

### This computer and WSL

```dotenv
MONITOR_SELF=true
WSL_AUTODETECT=true
```

`SELF` shows the machine running `start.cmd` / `server.py`. Opening the browser on another device does not change this source. Launching from Windows shows Windows; launching Python inside WSL shows that distribution's Linux environment. `SELF` always appears first in the menu.

Windows metrics come from system APIs, without SSH, a PowerShell collector or package installation. The disk is the Windows system drive; `DISK_PATH` applies only to Linux/WSL. Swap represents actual pagefiles rather than the commit limit. Unavailable metrics remain unknown; Linux load averages, iowait, steal and vnStat are unavailable on Windows. Processes inaccessible due to permissions are excluded from the corresponding ranking.

On Windows systems with multiple processor groups (typically more than 64 logical CPUs), overall CPU utilization is currently unknown because `GetSystemTimes` does not aggregate groups. Other metrics remain available.

WSL detection runs only on Windows and adds one menu entry per running distribution without rewriting configuration. Collection uses the standard Linux probe and `setsid`, without SSH or installing files. Stopped distributions are not intentionally started. If WSL stops during monitoring, its source loses connectivity. After manually starting the distribution, click Reconnect. Restart the dashboard to discover new distributions. Closing the monitor stops its own collectors without shutting down all of WSL.

For local sources only, set `servers.json` to an empty object `{}` and enable the desired flags. At least one source must be configured at startup. If there are no SSH servers or running WSL distributions, enable `MONITOR_SELF` or start a distribution. `--demo` ignores local flags and uses entirely synthetic data.

## Using the dashboard

The menu button hides or opens the server list. Every configured server collects from application startup, regardless of the selected view; switching views leaves other connections running. Interactive SSH authentication prompts are queued. Each server's last hour of history is stored separately in RAM and cleared on restart. Closing the browser tab leaves collection running. Pause freezes the selected view while collection continues. To stop, press `Ctrl+C` in the console. If CMD then asks `Terminate batch job (Y/N)?`, enter `Y` and press Enter; the monitor has already stopped.

After an SSH disconnect, the application attempts to reconnect. Three consecutive failed attempts stop automatic retries. Reconnect starts a new cycle for the selected server only. Receiving a valid sample resets the failure counter. Unavailable servers move down the list, while `SELF` stays first and the current selection is preserved. No new samples are recorded during a disconnect. Any password needed for another login is entered in the console again.

The RU/EN button at the top right switches the interface language and saves the selection in the browser. Documentation, API messages and application diagnostics are in English; Russian text is provided by the interface localization when `ru` is selected.

Linux RAM utilization uses `MemAvailable`. Older kernels without that field use `MemFree + Buffers + Cached + SReclaimable - Shmem`, clamped to total RAM. CPU utilization uses counter differences over the collection interval. MHz is a snapshot of the average frequency from `/proc/cpuinfo` at connection time and refreshes on reconnect.

On Raspberry Pi, an existing `vcgencmd measure_temp` command supplies CPU temperature in Celsius on each collection cycle, through the same SSH connection. It appears in a separate card below Server details. The API field is `latest.cpu.temperature_c`; unavailable readings are `null`. A missing, failed or timed-out command hides the card without stopping other metrics. No remote installation or elevated privileges are needed.

Swap without a configured partition or pagefile is shown as disabled. Disk utilization follows `df`: `used / (used + available)`, accounting for reserved blocks. With the standard interval, the disk is checked about every 10 seconds; intervals above 10 seconds check it on every cycle. Other cycles use the most recent result.

The top five processes come from native `ps` when it supports the required fields. Click CPU or Memory to see the five largest consumers in descending order. The collector sends the union of the top five by CPU and top five by RAM (at most ten processes), so a memory-heavy process remains available even with low CPU usage. Rows show PID, name, RAM and **average CPU since process startup**. This `ps` value can exceed 100% across multiple cores and differs from the current CPU utilization of the entire system. Command arguments are not collected. Load average, I/O wait and CPU steal help explain task queues, disk waits and competition for virtual machine CPU time.

Traffic is read about once a minute from an already installed vnStat using JSON API v2 (`vnstat --json d 7`). The monitor does not install or configure anything remotely. The seven calendar days include today on the server; missing readings remain unknown. Choose one interface when several are available. Interfaces are not summed, preventing duplicate tunnel traffic counts. The default-route interface is selected first when present in vnStat. Without the program, data or a supported JSON format, the traffic block is hidden. A failed or stalled optional command does not stop the main metrics.

The dashboard listens only on `127.0.0.1`. Each SSH server has one persistent connection. Browser requests read already collected state. Processes and seven-day traffic statistics belong only to the latest snapshot; the one-hour history holds graph data.

Click a traffic bar to see the date, received bytes, sent bytes and daily total. Weekly totals of at least 1 GiB stay in GiB instead of switching to TiB, making comparisons with daily vnStat reports easier. Smaller totals use appropriate units. 1024 GiB = 1 TiB. The interface picker supports arrow keys, Enter and Escape. Missing readings are shown as an em dash.

## Checks and demo mode

From a terminal in the application folder:

```powershell
.\start.cmd --check
.\start.cmd --demo
.\start.cmd --no-browser
```

`--check` validates local settings, files, Python and OpenSSH availability for SSH sources without connecting to a server. With `WSL_AUTODETECT`, it also lists running distributions without starting collectors. `--demo` shows clearly labelled synthetic data and works without SSH. `--no-browser` leaves opening the browser to you. Options can be combined, for example `start.cmd --demo --no-browser`.

On Linux/macOS with Python 3.11+, run `python3 server.py` from the project folder. Automatic Python preparation is for Windows.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| OpenSSH Client was not found | Open Start, find Optional features, add OpenSSH Client and launch again. Installing a missing Windows component may require administrator permissions. |
| `Could not resolve hostname` | Check the alias in `servers.json` and the selected `SSH_CONFIG`. The alias must match a `Host` entry in the SSH config for the same Windows account. |
| `Permission denied`, or the dashboard waits for a connection | Check the console for a password or passphrase prompt. Verify the user, key and login through Windows OpenSSH. Keep `SSH_BATCH_MODE=false` for interactive login. |
| Host key change warning | Verify the reason and correct fingerprint with the server owner. Keep SSH host key verification enabled. |
| Port is occupied | Close the previous monitor or set, for example, `PORT=8766` in `.env` and restart. |
| Python download failed | Check access to `https://www.python.org` and your proxy settings. Alternatively, install Python 3.11+ from the official website. For offline use, place the appropriate embeddable ZIP at the path shown in the error; the launcher verifies SHA-256. |
| SHA-256 verification failed | The archive was not executed. Retry from a trusted network or use an official installed Python. |
| Local Python cache is damaged | Close monitor windows and delete only the `.runtime\python-...` subfolder named in the error. The next launch rebuilds it from a verified archive. |
| Folder access denied | Move the fully extracted application to a regular writable folder and launch again. |
| Metrics are unavailable | Verify that the remote system is Linux, `DISK_PATH` exists and the SSH user can read `/proc` and run standard commands. |

A Windows administrator can install only the SSH client with:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

The native client is located at `C:\Windows\System32\OpenSSH\ssh.exe`. The launcher selects Windows OpenSSH to use its configuration, keys and console authentication.

Application errors are recorded in `logs/monitor.log`. SSH errors are in `logs/ssh-1.log`, `logs/ssh-2.log`, and so on, following `servers.json` order. Measurement history is not written to these files.

## Sources

The local Python version and SHA-256 hashes were pinned to the [official Python 3.14.8 release](https://www.python.org/downloads/release/python-3148/) on October 7, 2026. See the [embeddable package documentation](https://docs.python.org/3/using/windows.html#the-embeddable-package) and [OpenSSH Client installation guide](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse).

Traffic format and units: [official vnStat manual](https://humdi.net/vnstat/man/vnstat.html). Average process CPU and RSS: [procps ps manual](https://man7.org/linux/man-pages/man1/ps.1.html).

Connections to your servers and interactive authentication require separate verification. Further development instructions are in [AGENTS.md](../AGENTS.md).
