# Development guide

Read [docs/DESIGN.md](docs/DESIGN.md) before changing code. Setup and usage are
in [README.md](README.md) and [docs/USAGE.md](docs/USAGE.md).

## Constraints

- Python 3.11+, standard library only. The frontend uses plain HTML/CSS/JS.
- One persistent Windows OpenSSH process and one remote collector per connection. HTTP polling reads cached data without starting additional SSH sessions.
- Send the shell script through stdin as exact UTF-8 bytes with LF endings. Do not replace binary writes with `TextIOWrapper.write`: Windows would add CRLF and break the Linux script.
- Remote commands only read data. No package installation, `sudo`, services or saved scripts are required on the Linux server.
- The OpenSSH user comes from the existing config and may be a regular user or `root`. Preserve support for aliases, ports, keys and `ProxyJump`.
- OpenSSH handles passwords and private keys. Do not add them to application configuration, the API, logs, source files or ZIP archives.
- Preserve normal host key verification. Do not use `StrictHostKeyChecking=no`, disable `known_hosts`, automatically accept unknown keys or bypass TLS verification when downloading Python.
- Listen only on `127.0.0.1`. Preserve the API token, Host/Origin validation, fixed static routes and absence of an HTTP interface for executing commands.
- Real mode never substitutes invented values. Missing metrics are `null`; disabled swap is explicitly identified.
- History is limited to one hour and stored in RAM. Pausing the interface leaves collection running.
- Collect all configured servers from startup, with separate histories. Serialize interactive SSH authentication. Reconnect affects only the selected server. Processes and traffic belong only to the latest snapshot.
- `MONITOR_SELF` and `WSL_AUTODETECT` are disabled by default. `SELF` means the machine running Python. Detect WSL only on Windows and only distributions already running; do not rewrite configuration. Stop only the collector's own process group, never an entire distribution with `wsl --terminate` or `--shutdown`.
- The process list uses the native `ps` average CPU since process startup. Do not present it as instantaneous utilization. Do not collect command arguments.
- For CPU/RAM sorting, send the union of the top five processes for each metric (at most ten records); the interface displays the five selected leaders.
- After three consecutive unsuccessful SSH sessions, wait for manual reconnect. A successful frame or manual reconnect resets the counter. Waiting must be interrupted by application shutdown.
- Read vnStat only: JSON API v2, the server's last seven calendar days, refreshed about once a minute. Do not install anything remotely, sum interfaces or replace gaps with zeros. Hide the block when no data is available.
- CPU uses counter deltas; MHz is a connection-time snapshot. RAM uses `MemAvailable` or, on older kernels, `MemFree + Buffers + Cached + SReclaimable - Shmem`, clamped between zero and total RAM.
- Check disks about every 10 seconds, rounded to collection cycles; with a longer interval, check every cycle. Preserve the `df` timeout and continue other metrics after disk errors.
- Documentation, comments, application diagnostics and API messages are English. Keep Russian text only in the frontend localization, displayed when `ru` is selected. English views must not contain Russian labels, messages or tooltips.

## Checks

Run from the project root with Python 3.11+. Node checks are optional if Node
is unavailable; Node is not an application dependency.

```text
python -m unittest discover -s tests -v
python -m compileall -q server.py monitor tests
node --check static/app.js
node tests/test_frontend.cjs
python server.py --demo --check
```

For manual UI checks, run `python server.py --demo --no-browser`. Stop test
processes and their children afterward. Do not present JS function checks as
verification in a real browser.

On Windows, parse `start.ps1` with
`System.Management.Automation.Language.Parser.ParseFile` and fail on parse errors
without executing the launcher.

Check double-click launch from a path containing spaces, Unicode and `!`;
first launch without Python; offline relaunch; installed Python; missing OpenSSH;
occupied port; invalid configuration; and retention of the error window.
Demo mode must work without OpenSSH.

With an isolated SSH server, check a regular user, sustained frames, disconnect
and recovery. Verify passwords, passphrases and host key prompts in a real
Windows console. Report automated tests, browser checks and actual Windows
launches separately; Linux checks do not verify Windows behavior.

## Local Python

`start.ps1` is authoritative for the pinned runtime version and hashes. When
updating, verify all three official ZIP archives and SHA-256 hashes at python.org;
update version and hashes together. Verify before extracting or executing.
Keep the standard library, runtime directory and relative application path
`../..` in the runtime's `._pth` file, without enabling `site` or `pip`.
The cache is in `.runtime`; publish only complete, verified runtime directories.
Change only the process environment, never persistent Windows or SSH settings.

## Packaging

Include safe-default `.env` and `servers.json`, their example files, both
launchers, README, AGENTS, LICENSE, application code, static assets, documentation and
tests. ZIP paths must be relative.
Exclude runtimes, caches, logs, temporary files, private keys, actual user
addresses/aliases and secrets. Check filenames and links, and keep README,
`.env.example` and the API contract consistent with the code.
