from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _icalbuddy_available() -> bool:
    if os.environ.get("MEETINGCTL_ICALBUDDY_UNAVAILABLE") == "1":
        return False
    explicit = os.environ.get("MEETINGCTL_ICALBUDDY_BIN", "").strip()
    if explicit:
        return Path(explicit).expanduser().exists()
    candidates = [
        Path("~/icalBuddy/icalBuddy").expanduser(),
        Path("/usr/local/bin/icalBuddy"),
    ]
    if any(candidate.exists() for candidate in candidates):
        return True
    return shutil.which("icalBuddy") is not None

try:
    from EventKit import EKEventStore, EKEntityTypeEvent
except ImportError:
    EKEventStore = None  # type: ignore[misc, assignment]
    EKEntityTypeEvent = None  # type: ignore[misc, assignment]


def run_doctor() -> dict[str, object]:
    if os.environ.get("MEETINGCTL_TEST_DOCTOR_ALL_OK") == "1":
        return {
            "ok": True,
            "checks": [
                {"name": "vault_path", "ok": True, "message": "Vault path is set.", "hint": ""},
                {"name": "recordings_path", "ok": True, "message": "Recordings path is set.", "hint": ""},
                {"name": "calendar_backend", "ok": True, "message": "At least one calendar backend is available.", "hint": ""},
                {"name": "ffmpeg", "ok": True, "message": "ffmpeg available.", "hint": ""},
                {"name": "calendar_permissions", "ok": True, "message": "Calendar access authorized.", "hint": ""},
                {"name": "eventkit_helper", "ok": True, "message": "EventKit helper is available.", "hint": ""},
                {"name": "audio_hijack", "ok": True, "message": "Audio Hijack installed.", "hint": ""},
            ],
        }

    checks: list[dict[str, object]] = []

    vault_path = os.environ.get("VAULT_PATH")
    checks.append(
        {
            "name": "vault_path",
            "ok": bool(vault_path),
            "message": "Vault path is set." if vault_path else "Vault path is missing.",
            "hint": "Set VAULT_PATH in your configured env file.",
        }
    )

    recordings_path = os.environ.get("RECORDINGS_PATH")
    checks.append(
        {
            "name": "recordings_path",
            "ok": bool(recordings_path),
            "message": "Recordings path is set." if recordings_path else "Recordings path is missing.",
            "hint": "Set RECORDINGS_PATH in your configured env file.",
        }
    )

    eventkit_available = os.environ.get("MEETINGCTL_EVENTKIT_UNAVAILABLE") != "1"
    jxa_available = os.environ.get("MEETINGCTL_JXA_UNAVAILABLE") != "1"
    icalbuddy_available = _icalbuddy_available()
    checks.append(
        {
            "name": "calendar_backend",
            "ok": eventkit_available or jxa_available or icalbuddy_available,
            "message": (
                "At least one calendar backend is available."
                if (eventkit_available or jxa_available or icalbuddy_available)
                else "No calendar backend available."
            ),
            "hint": "Enable EventKit, JXA, or icalBuddy, then run `meetingctl doctor` again.",
        }
    )

    ffmpeg_ok = shutil.which("ffmpeg") is not None
    checks.append(
        {
            "name": "ffmpeg",
            "ok": ffmpeg_ok,
            "message": "ffmpeg available." if ffmpeg_ok else "ffmpeg not found.",
            "hint": "Install ffmpeg (e.g., `brew install ffmpeg`).",
        }
    )

    # Check EventKit calendar permissions
    if EKEventStore is not None:
        auth_status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
        # EKAuthorizationStatus values vary by OS:
        # 0=NotDetermined, 1=Restricted, 2=Denied, 3=WriteOnly/Authorized, 4=FullAccess.
        calendar_ok = auth_status in (3, 4)
        status_names = {
            0: "not determined",
            1: "restricted",
            2: "denied",
            3: "authorized",
            4: "authorized (full access)",
        }
        status_name = status_names.get(auth_status, "unknown")
        checks.append(
            {
                "name": "calendar_permissions",
                "ok": calendar_ok,
                "message": f"Calendar access {status_name}.",
                "hint": "Grant calendar access in System Settings > Privacy & Security > Calendars.",
            }
        )
    else:
        checks.append(
            {
                "name": "calendar_permissions",
                "ok": False,
                "message": "EventKit framework not available.",
                "hint": "Install pyobjc-framework-EventKit.",
            }
        )

    helper_path = Path(__file__).resolve().parents[2] / "scripts" / "eventkit_fetch.py"
    checks.append(
        {
            "name": "eventkit_helper",
            "ok": helper_path.exists() and os.access(helper_path, os.X_OK),
            "message": "EventKit helper is available."
            if (helper_path.exists() and os.access(helper_path, os.X_OK))
            else "EventKit helper missing or not executable.",
            "hint": "Ensure scripts/eventkit_fetch.py exists and is executable.",
        }
    )

    # Check Audio Hijack installation
    try:
        result = subprocess.run(
            ["mdfind", "kMDItemFSName == 'Audio Hijack.app'"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        audio_hijack_found = bool(result.stdout.strip())
        checks.append(
            {
                "name": "audio_hijack",
                "ok": audio_hijack_found,
                "message": "Audio Hijack installed." if audio_hijack_found else "Audio Hijack not found.",
                "hint": "Install Audio Hijack from https://rogueamoeba.com/audiohijack/",
            }
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        checks.append(
            {
                "name": "audio_hijack",
                "ok": False,
                "message": "Could not check Audio Hijack installation.",
                "hint": "Ensure Spotlight indexing is enabled.",
            }
        )

    # Keep optional-path checks lightweight and actionable.
    if vault_path:
        checks.append(
            {
                "name": "vault_path_absolute",
                "ok": Path(vault_path).expanduser().is_absolute(),
                "message": "Vault path is absolute."
                if Path(vault_path).expanduser().is_absolute()
                else "Vault path is not absolute.",
                "hint": "Use an absolute VAULT_PATH for reliable cross-tool behavior.",
            }
        )

    ok = all(bool(check["ok"]) for check in checks if check["name"] != "ffmpeg")
    return {"ok": ok, "checks": checks}
