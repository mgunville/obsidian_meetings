from __future__ import annotations

import os
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _load_zoneinfo(name: str) -> tzinfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return None


def _zone_name_from_localtime(path: Path = Path("/etc/localtime")) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        return ""
    marker = "/zoneinfo/"
    resolved_str = str(resolved)
    if marker not in resolved_str:
        return ""
    return resolved_str.split(marker, 1)[1].strip()


def local_timezone() -> tzinfo:
    override = os.environ.get("MEETINGCTL_LOCAL_TIMEZONE", "").strip()
    zone = _load_zoneinfo(override)
    if zone is not None:
        return zone

    current = datetime.now().astimezone().tzinfo
    if isinstance(current, ZoneInfo):
        return current

    zone = _load_zoneinfo(os.environ.get("TZ", "").strip())
    if zone is not None:
        return zone

    zone = _load_zoneinfo(_zone_name_from_localtime())
    if zone is not None:
        return zone

    timezone_file = Path("/etc/timezone")
    try:
        zone = _load_zoneinfo(timezone_file.read_text(encoding="utf-8").strip())
    except OSError:
        zone = None
    if zone is not None:
        return zone

    return current or UTC
