# Server Monitor

A local dashboard for CPU, RAM, swap, disks and processes across Linux servers.
Also supports this computer, running WSL distributions and optional vnStat traffic.

Runs on Windows 10/11 with Windows OpenSSH Client for remote servers. Uses Python
3.11+; the launcher finds an existing installation or downloads a SHA-256-verified
local runtime. No Python packages or remote installations are needed.

## Quick start

1. Clone the repository or extract the ZIP into a writable folder.
2. Create missing configuration files: copy `.env.example` to `.env` and
   `servers.json.example` to `servers.json`. Keep existing files when upgrading.
3. Map server names to existing OpenSSH `Host` aliases in `servers.json`:

   ```json
   {
     "Production": "my-server",
     "Backup": "my-backup"
   }
   ```

4. Set `LANGUAGE=en` or `LANGUAGE=ru` in `.env`.
5. Double-click `start.cmd` and keep the console open for SSH prompts.
   Verify a new host key's fingerprint before accepting it. Passwords and private
   keys belong to OpenSSH, never to the application configuration.

Open [127.0.0.1:8765](http://127.0.0.1:8765) if the browser does not open automatically.
The first launch needs Internet access if Python is missing.

To stop, press **Ctrl+C** in the console. If CMD asks to terminate the batch job,
enter **Y**. Closing the browser leaves monitoring running.

## Useful commands

Run from the project folder:

```powershell
.\start.cmd --demo        # Preview with synthetic data; no SSH required
.\start.cmd --check       # Check local setup without connecting to servers
.\start.cmd --no-browser  # Start without opening the browser
```

## Using it

Switch servers in the sidebar, choose a 5/15/60-minute history window, or pause
the view. Every source keeps collecting while you switch or pause. History stays
in RAM for one hour. After three failed SSH sessions, click **Reconnect** to retry.

Optional local sources are disabled by default. Set `MONITOR_SELF=true` in `.env`
to monitor this computer, or `WSL_AUTODETECT=true` to include running WSL distributions.
For local sources only, use `{}` in `servers.json`.

## Documentation

- [User guide](docs/USAGE.md): settings, jump hosts, metrics and troubleshooting.
- [Architecture and API](docs/DESIGN.md).

Licensed under the [MIT License](LICENSE).
