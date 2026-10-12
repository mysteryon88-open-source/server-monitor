"""Linux procfs/df parsing and stateful metric arithmetic, with no dependencies.

The wire format is a sequence of tab-prefixed records inside __SM_BEGIN__ and
__SM_END__ lines. Unknown or malformed records are ignored; a missing metric
remains None. The remote shell never evaluates operating-system metadata.

MemAvailable is used when Linux provides it. The older-kernel fallback is an
estimate: MemFree + Buffers + Cached + SReclaimable - Shmem, clamped to RAM.
CPU busy excludes idle and iowait; user/nice already include guest time, so
only the first eight /proc/stat counters contribute to the total.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
import math
from pathlib import Path
import re
import shlex
import time
from typing import Any


_MEMORY_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_()]*):\s+([0-9]+)\s+kB\s*$")
_DF_LINE = re.compile(r"^\s*(.+?)\s+([0-9]+)\s+([0-9]+)\s+(-?[0-9]+)\s+([0-9]+)%\s+(.+?)\s*$")
_OS_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UINT64_MAX = (1 << 64) - 1
_TRAFFIC_MAX_BYTES = 49152
_TRAFFIC_MAX_INTERFACES = 32
_INTERFACE_NAME = re.compile(r"^[A-Za-z0-9_.:@-]{1,32}$")


def _integer(value: str, *, signed: bool = False) -> int | None:
    try:
        number = int(value)
    except (ValueError, TypeError):
        return None
    if abs(number) > _UINT64_MAX or (not signed and number < 0):
        return None
    return number


def _number(value: str) -> float | None:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _os_release_value(value: str) -> str | None:
    """Decode quoted data without shell expansion, command execution or eval."""
    try:
        words = shlex.split(value.strip(), comments=False, posix=True)
    except ValueError:
        return None
    return " ".join(words) if words else ""


def _traffic(payload: str | None, today: str | None, default: str | None,
             updated_at: int) -> dict[str, Any] | None:
    """Read vnStat JSON API v2 byte counters; older units are unsupported."""
    if not isinstance(payload, str) or len(payload.encode("utf-8")) > _TRAFFIC_MAX_BYTES:
        return None
    try:
        if not isinstance(today, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", today):
            return None
        last = date.fromisoformat(today)
        dates = [(last - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
        source = json.loads(payload)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None
    if not isinstance(source, dict) or source.get("jsonversion") != "2":
        return None
    interfaces = source.get("interfaces")
    if not isinstance(interfaces, list) or not 1 <= len(interfaces) <= _TRAFFIC_MAX_INTERFACES:
        return None
    result = []
    seen = set()
    for interface in interfaces:
        if not isinstance(interface, dict):
            return None
        name = interface.get("name")
        if not isinstance(name, str) or not _INTERFACE_NAME.fullmatch(name) or name in seen:
            return None
        seen.add(name)
        traffic = interface.get("traffic")
        entries = traffic.get("day") if isinstance(traffic, dict) else None
        if not isinstance(entries, list) or len(entries) > 7:
            return None
        daily = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("date"), dict):
                return None
            parts = entry["date"]
            if any(type(parts.get(key)) is not int for key in ("year", "month", "day")):
                return None
            try:
                day = date(parts["year"], parts["month"], parts["day"]).isoformat()
            except (ValueError, OverflowError):
                return None
            if day in daily:
                return None
            counts = {}
            for key in ("rx", "tx"):
                value = entry.get(key)
                counts[key] = value if type(value) is int and 0 <= value <= _UINT64_MAX else None
            daily[day] = counts
        days = [{"date": day, "rx": daily.get(day, {}).get("rx"),
                 "tx": daily.get(day, {}).get("tx")} for day in dates]
        totals = {}
        for key in ("rx", "tx"):
            known = [day[key] for day in days if day[key] is not None]
            totals[key] = sum(known) if known else None
        if any(value is not None and value > _UINT64_MAX for value in totals.values()):
            return None
        result.append({"name": name, "days": days, **totals})
    if not any(interface[key] is not None for interface in result for key in ("rx", "tx")):
        return None
    return {"updated_at": updated_at,
            "default_interface": default if default in seen else result[0]["name"],
            "interfaces": result}


def parse_frame(text: str) -> dict[str, Any]:
    """Parse one frame with or without its delimiters.

    Memory and disk sizes in the returned raw mapping are bytes. CPU counters
    are the eight Linux accounting fields, with absent older-kernel fields
    padded with zero; guest/guest_nice are deliberately excluded.
    """
    raw: dict[str, Any] = {"meminfo": {}, "os_release": {}, "disk_path": "/"}
    # Only LF delimits records. Unicode separators can be legal path data.
    for line in text.split("\n"):
        line = line.removesuffix("\r")
        key, separator, value = line.partition("\t")
        if not separator:
            continue
        if key == "cpu":
            fields = value.split()
            counters = [_integer(item) for item in fields[:8]]
            if len(counters) >= 4 and all(item is not None for item in counters):
                raw["cpu"] = tuple(counters + [0] * (8 - len(counters)))
            else:
                raw.pop("cpu", None)
        elif key == "meminfo":
            match = _MEMORY_LINE.fullmatch(value)
            if match:
                count = _integer(match[2])
                if count is not None:
                    raw["meminfo"][match[1]] = count * 1024
        elif key in ("cores", "btime"):
            count = _integer(value)
            if count is not None and (key != "cores" or count > 0):
                raw[key] = count
        elif key in ("uptime", "mhz"):
            number = _number(value)
            if number is not None and (key != "mhz" or number > 0):
                raw[key] = number
        elif key == "load":
            values = [_number(item) for item in value.split()]
            if len(values) == 3 and all(item is not None for item in values):
                raw[key] = values
        elif key in ("hostname", "kernel", "arch", "model", "boot_id", "disk_path"):
            if value:
                raw[key] = value
        elif key == "processes_available":
            raw["processes"] = [] if value == "1" else None
        elif key == "process" and isinstance(raw.get("processes"), list):
            fields = value.split(None, 3)
            if len(fields) == 4 and len(raw["processes"]) < 10:
                pid = _integer(fields[0])
                rss = _integer(fields[2])
                name = fields[3]
                if pid and len(name) <= 128 and not any(ord(c) < 32 or ord(c) == 127 for c in name):
                    raw["processes"].append({"pid": pid, "name": name,
                                             "cpu_percent": _number(fields[1]),
                                             "memory_bytes": rss * 1024 if rss is not None and rss <= _UINT64_MAX // 1024 else None})
        elif key == "traffic_refresh":
            raw[key] = value == "1"
        elif key in ("traffic_date", "default_interface"):
            raw[key] = value
        elif key == "vnstat":
            raw["traffic_refresh"] = True
            raw[key] = value if len(value.encode("utf-8")) <= _TRAFFIC_MAX_BYTES else None
        elif key == "os_release":
            name, equals, encoded = value.partition("=")
            if equals and _OS_KEY.fullmatch(name):
                decoded = _os_release_value(encoded)
                if decoded is not None:
                    raw["os_release"][name] = decoded
        elif key == "df":
            match = _DF_LINE.fullmatch(value)
            if not match:
                continue
            total = _integer(match[2])
            used = _integer(match[3])
            available = _integer(match[4], signed=True)
            if None not in (total, used, available):
                raw["disk"] = {
                    "device": match[1], "total": total * 1024,
                    "used": used * 1024, "available": available * 1024,
                }
    return raw


def _percent(used: int, denominator: int) -> float | None:
    return round(used / denominator * 100.0, 1) if denominator > 0 else None


class MetricCalculator:
    """Convert parsed frames to API samples; create a new instance per SSH link."""

    def __init__(self) -> None:
        self._previous: dict[str, Any] | None = None
        self._traffic: dict[str, Any] | None = None

    def _cpu(self, raw: dict[str, Any], received: float) -> dict[str, Any]:
        result = {
            "percent": None, "cores": raw.get("cores"), "mhz": raw.get("mhz"),
            "model": raw.get("model"), "iowait": None, "steal": None,
        }
        counters = raw.get("cpu")
        if counters is None:
            self._previous = None
            return result
        current = {
            "cpu": tuple(counters), "ts": received, "uptime": raw.get("uptime"),
            "boot_id": raw.get("boot_id"), "btime": raw.get("btime"),
            "cores": raw.get("cores"),
        }
        previous = self._previous
        self._previous = current
        if previous is None or received <= previous["ts"]:
            return result
        for identity in ("boot_id", "btime", "cores"):
            before, after = previous[identity], current[identity]
            if before is not None and after is not None and before != after:
                return result
        if (previous["uptime"] is not None and current["uptime"] is not None
                and current["uptime"] <= previous["uptime"]):
            return result
        deltas = [after - before for before, after in zip(previous["cpu"], current["cpu"])]
        total = sum(deltas)
        # Linux iowait can occasionally decrease. Treat that interval as
        # unknown as well, instead of drawing an invented negative activity.
        if len(deltas) != 8 or total <= 0 or any(delta < 0 for delta in deltas):
            return result
        result["percent"] = _percent(total - deltas[3] - deltas[4], total)
        result["iowait"] = _percent(deltas[4], total)
        result["steal"] = _percent(deltas[7], total)
        return result

    def update(self, raw: dict[str, Any], timestamp: float | None = None) -> dict[str, Any]:
        """Return a JSON-safe sample, using local receive time in milliseconds."""
        received = time.time() if timestamp is None else float(timestamp)
        if not math.isfinite(received) or not math.isfinite(received * 1000):
            raise ValueError("timestamp must be finite")
        if raw.get("traffic_refresh"):
            self._traffic = _traffic(raw.get("vnstat"), raw.get("traffic_date"),
                                     raw.get("default_interface"), round(received * 1000))

        info = raw.get("meminfo", {})
        total = info.get("MemTotal")
        memory = {"percent": None, "used": None, "total": total, "available": None}
        if total is not None and total > 0:
            available = info.get("MemAvailable")
            if available is None and "MemFree" in info:
                available = (info["MemFree"] + info.get("Buffers", 0)
                             + info.get("Cached", 0) + info.get("SReclaimable", 0)
                             - info.get("Shmem", 0))
            if available is not None:
                available = max(0, min(total, available))
                memory.update(available=available, used=total - available,
                              percent=_percent(total - available, total))

        swap_total = info.get("SwapTotal")
        swap = {"percent": None, "used": None, "total": swap_total, "enabled": None}
        if swap_total is not None:
            swap["enabled"] = swap_total > 0
            if swap_total == 0:
                swap.update(percent=0.0, used=0)
            elif "SwapFree" in info:
                used = swap_total - max(0, min(swap_total, info["SwapFree"]))
                swap.update(percent=_percent(used, swap_total), used=used)

        disk = {"percent": None, "used": None, "total": None, "available": None,
                "path": raw.get("disk_path", "/"), "device": None}
        if raw.get("disk"):
            disk.update(raw["disk"])
            # df reserves blocks for privileged users on some filesystems.
            # Its denominator is used+available, not the physical block total.
            disk["percent"] = _percent(disk["used"], disk["used"] + disk["available"])

        release = raw.get("os_release", {})
        os_name = release.get("PRETTY_NAME")
        if not os_name and release.get("NAME"):
            os_name = " ".join(part for part in (release["NAME"], release.get("VERSION")) if part)
        return {
            "ts": round(received * 1000), "cpu": self._cpu(raw, received),
            "memory": memory, "swap": swap, "disk": disk,
            "processes": raw.get("processes"), "traffic": self._traffic,
            "host": {"hostname": raw.get("hostname"), "os": os_name,
                     "kernel": raw.get("kernel"), "arch": raw.get("arch"),
                     "uptime": raw.get("uptime"), "load": raw.get("load")},
        }


def build_probe(interval: int = 2, disk_path: str = "/") -> str:
    """Build a POSIX shell sampler, safely quoting its absolute disk path.

    No script or data files are created remotely. OS, CPU model and clock
    metadata are read once at connection; counters, online cores, memory,
    load and uptime are refreshed per frame. Disk is polled every 10 seconds
    (or every interval if longer), with a timeout or a shell watchdog. GNU ps
    is optional; an existing vnStat v2 database is read about once per minute.
    """
    if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
        raise ValueError("interval must be a positive integer number of seconds")
    if (not isinstance(disk_path, str) or not disk_path.startswith("/")
            or any(ord(character) < 32 or ord(character) == 127 for character in disk_path)):
        raise ValueError("disk_path must be an absolute Linux path without control characters")
    template = Path(__file__).with_name("probe.sh").read_text(encoding="utf-8")
    return template.replace("__SM_INTERVAL__", str(interval)).replace("__SM_DISK_PATH__", shlex.quote(disk_path))
