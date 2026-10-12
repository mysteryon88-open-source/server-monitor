"""Read .env as data, never as commands or interpolated shell source."""

from __future__ import annotations

import os
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """An actionable, non-secret configuration error."""


@dataclass(frozen=True)
class Config:
    base_dir: Path
    alias: str
    port: int = 8765
    interval: int = 2
    disk_path: str = "/"
    batch_mode: bool = False
    ssh_config: Path | None = None
    demo: bool = False
    language: str = "ru"
    servers: dict[str, str | dict[str, str]] = field(default_factory=dict)
    monitor_self: bool = False
    wsl_autodetect: bool = False
    jump: str | None = None


KEYS = {"PORT", "INTERVAL", "DISK_PATH", "SSH_BATCH_MODE", "SSH_CONFIG", "LANGUAGE",
        "MONITOR_SELF", "WSL_AUTODETECT"}


def load_servers(path: Path, *, allow_empty: bool = False) -> dict[str, str | dict[str, str]]:
    """Read a bounded name-to-alias mapping; never accept SSH command options."""
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ConfigError("Duplicate server name in servers.json.")
            result[key] = value
        return result

    try:
        if path.stat().st_size > 65536:
            raise ConfigError("servers.json must be smaller than 64 KiB.")
        servers = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError("Cannot read servers.json: " + str(exc) + ". Copy servers.json.example if needed.") from exc
    if not isinstance(servers, dict) or not (0 if allow_empty else 1) <= len(servers) <= 32:
        raise ConfigError("servers.json must map 1 to 32 server names to SSH aliases (empty only with local monitoring enabled).")
    routes = set()
    for name, entry in servers.items():
        if (not name.strip() or len(name) > 80
                or any(unicodedata.category(c) in {"Cc", "Cs"} for c in name)):
            raise ConfigError("Server names must contain 1 to 80 characters without control characters.")
        if isinstance(entry, dict):
            if 'alias' not in entry or set(entry) - {'alias', 'jump'}:
                raise ConfigError("Server objects accept only alias and optional jump.")
            aliases = list(entry.values())
            route = (entry['alias'], entry.get('jump'))
        else:
            aliases = [entry]
            route = (entry, None)
        if any(not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:+-]{0,252}", alias)
               for alias in aliases):
            raise ConfigError("Each SSH alias/jump in servers.json must be a name without spaces, shell syntax or leading '-'.")
        if route in routes:
            raise ConfigError("Each SSH alias and jump route in servers.json must be listed only once.")
        routes.add(route)
    return servers


def parse_env(text: str) -> dict[str, str]:
    """Support UTF-8/BOM, simple quotes and comments; preserve Windows slashes."""
    result: dict[str, str] = {}
    for number, original in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise ConfigError(f".env, line {number}: expected KEY=value.")
        key, value = match.groups()
        if key in result:
            raise ConfigError(f".env, line {number}: duplicate {key}.")
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].strip().startswith("#")):
                raise ConfigError(f".env, line {number}: unclosed or invalid quoted value.")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        result[key] = value
    return result


def _integer(values: dict[str, str], key: str, default: int, low: int, high: int) -> int:
    text = values.get(key, str(default))
    if not re.fullmatch(r"[0-9]+", text):
        raise ConfigError(f"{key} must be an integer between {low} and {high}.")
    value = int(text)
    if not low <= value <= high:
        raise ConfigError(f"{key} must be between {low} and {high}.")
    return value


def _boolean(values: dict[str, str], key: str) -> bool:
    value = values.get(key, 'false').lower()
    if value not in {'true', 'false', '1', '0', 'yes', 'no'}:
        raise ConfigError(f'{key} must be true or false.')
    return value in {'true', '1', 'yes'}


def load_config(base_dir: Path, env_path: Path | None = None,
                environ: Mapping[str, str] | None = None, *, demo: bool = False,
                port_override: int | None = None, servers_path: Path | None = None) -> Config:
    base_dir = base_dir.resolve()
    env_file = env_path if env_path is not None else base_dir / ".env"
    try:
        values = parse_env(env_file.read_text(encoding="utf-8-sig")) if env_file.exists() else {}
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"Cannot read .env as UTF-8: {exc}") from exc
    unknown = set(values) - KEYS
    if unknown:
        if "SSH_ALIAS" in unknown:
            raise ConfigError("Move SSH_ALIAS from .env to servers.json as {\"Server name\": \"ssh-alias\"}.")
        raise ConfigError("Unknown .env option(s): " + ", ".join(sorted(unknown)))
    environment = os.environ if environ is None else environ
    values.update({key: environment[key] for key in KEYS if key in environment})
    monitor_self = _boolean(values, 'MONITOR_SELF')
    wsl_autodetect = _boolean(values, 'WSL_AUTODETECT')
    if demo:
        servers = {"Demo NL": "demo-nl", "Demo RU": "demo-ru", "Demo backup": "demo-backup"}
    else:
        servers = load_servers(servers_path if servers_path is not None else base_dir / "servers.json",
                               allow_empty=monitor_self or wsl_autodetect)
    first = next(iter(servers.values()), '')
    alias = first['alias'] if isinstance(first, dict) else first
    language = values.get("LANGUAGE", "ru").lower()
    if language not in {"ru", "en"}:
        raise ConfigError("LANGUAGE must be ru or en.")
    port = _integer(values, "PORT", 8765, 1, 65535)
    if port_override is not None:
        if not 1 <= port_override <= 65535:
            raise ConfigError("--port must be between 1 and 65535.")
        port = port_override
    interval = _integer(values, "INTERVAL", 2, 1, 60)
    disk_path = values.get("DISK_PATH", "/")
    if not disk_path.startswith("/") or len(disk_path) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in disk_path):
        raise ConfigError("DISK_PATH must be an absolute Linux path without control characters.")
    batch = _boolean(values, 'SSH_BATCH_MODE')
    config_name = values.get("SSH_CONFIG", "").strip()
    ssh_config = None
    if config_name and not demo:
        if any(ord(c) < 32 for c in config_name):
            raise ConfigError("SSH_CONFIG must not contain control characters.")
        ssh_config = Path(os.path.expandvars(config_name)).expanduser()
        if not ssh_config.is_absolute():
            ssh_config = base_dir / ssh_config
        if not ssh_config.is_file():
            raise ConfigError("SSH_CONFIG does not point to an existing file.")
        ssh_config = ssh_config.resolve()
    return Config(base_dir, alias, port, interval, disk_path,
                  batch, ssh_config, demo, language, servers,
                  monitor_self and not demo, wsl_autodetect and not demo,
                  first.get('jump') if isinstance(first, dict) else None)
