from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    from EventKit import EKEventStore, EKEntityTypeEvent
    from Foundation import NSDate
except ImportError:
    EKEventStore = None  # type: ignore[misc, assignment]
    EKEntityTypeEvent = None  # type: ignore[misc, assignment]
    NSDate = None  # type: ignore[misc, assignment]


class BackendUnavailableError(RuntimeError):
    pass


class EventKitBackend:
    backend_name = "eventkit"

    def __init__(
        self,
        loader: Callable[..., list[dict[str, object]]] | None = None,
    ) -> None:
        self._loader = loader or self._default_loader

    def _default_loader(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, object]]:
        if os.environ.get("MEETINGCTL_EVENTKIT_UNAVAILABLE") == "1":
            raise BackendUnavailableError("EventKit backend unavailable on this machine.")

        # Allow env var override for testing
        if "MEETINGCTL_EVENTKIT_EVENTS_JSON" in os.environ:
            raw = os.environ.get("MEETINGCTL_EVENTKIT_EVENTS_JSON", "[]")
            payload = json.loads(raw)
            if not isinstance(payload, list):
                raise RuntimeError("Invalid EventKit payload")
            return payload

        helper = os.environ.get("MEETINGCTL_EVENTKIT_HELPER")
        if helper:
            return _run_eventkit_helper(Path(helper).expanduser(), start=start, end=end)

        helper_mode = os.environ.get("MEETINGCTL_EVENTKIT_HELPER_MODE", "auto").lower()
        default_helper = _default_eventkit_helper_path()
        if helper_mode in {"auto", "helper"} and default_helper.exists():
            try:
                return _run_eventkit_helper(default_helper, start=start, end=end)
            except Exception:
                if helper_mode == "helper":
                    raise

        # Check if EventKit is available
        if EKEventStore is None:
            raise BackendUnavailableError(
                "EventKit framework not available. Install pyobjc-framework-EventKit."
            )

        # Check authorization status
        # EKAuthorizationStatus values: 0=NotDetermined, 1=Restricted, 2=Denied, 3=Authorized
        auth_status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
        if auth_status == 2:  # Denied
            raise BackendUnavailableError(
                "Calendar access denied. Grant permission in System Settings > Privacy & Security > Calendars."
            )
        if auth_status == 1:  # Restricted
            raise BackendUnavailableError(
                "Calendar access restricted by system policy."
            )

        # Create event store
        store = EKEventStore.alloc().init()

        # Query events for the next 7 days
        # Use NSDate instead of Python datetime to avoid timezone issues with PyObjC
        if start and end:
            start_date = NSDate.dateWithTimeIntervalSince1970_(start.timestamp())
            end_date = NSDate.dateWithTimeIntervalSince1970_(end.timestamp())
        else:
            now_ns = NSDate.date()
            start_date = now_ns.dateByAddingTimeInterval_(-3600)  # 1 hour ago
            end_date = now_ns.dateByAddingTimeInterval_(7 * 24 * 3600)  # 7 days later

        # Create predicate for date range
        predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
            start_date, end_date, None
        )

        # Fetch events
        events = store.eventsMatchingPredicate_(predicate)

        # Normalize to common schema
        normalized = []
        for event in events:
            title = event.title() if event.title() else ""
            start = event.startDate()
            end = event.endDate()
            calendar = event.calendar()
            calendar_name = calendar.title() if calendar else ""
            location = event.location() if event.location() else ""
            notes = event.notes() if event.notes() else ""
            url = event.URL()
            url_str = str(url) if url else ""

            normalized.append({
                "title": title,
                "start": _normalize_datetime_string(start.description()) if start else "",
                "end": _normalize_datetime_string(end.description()) if end else "",
                "calendar_name": calendar_name,
                "location": location,
                "notes": notes,
                "url": url_str,
            })

        return normalized

    def fetch_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, object]]:
        try:
            return self._loader(start=start, end=end)
        except TypeError:
            # Backward compatible path for tests/injected loaders that do not accept kwargs.
            return self._loader()


class JXABackend:
    backend_name = "jxa"

    def __init__(
        self,
        loader: Callable[..., list[dict[str, object]]] | None = None,
    ) -> None:
        self._loader = loader or self._default_loader

    def _default_loader(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, object]]:
        if os.environ.get("MEETINGCTL_JXA_UNAVAILABLE") == "1":
            raise RuntimeError("JXA backend unavailable on this machine.")

        # Allow env var override for testing
        if "MEETINGCTL_JXA_EVENTS_JSON" in os.environ:
            raw = os.environ.get("MEETINGCTL_JXA_EVENTS_JSON", "[]")
            payload = json.loads(raw)
            if not isinstance(payload, list):
                raise RuntimeError("Invalid JXA payload")
            return payload

        jxa_script_path = os.environ.get("MEETINGCTL_JXA_SCRIPT")
        if not jxa_script_path:
            default_script = Path(__file__).resolve().parents[3] / "scripts" / "calendar_events.jxa"
            if default_script.exists():
                jxa_script_path = str(default_script)

        if jxa_script_path:
            command = ["osascript", "-l", "JavaScript", jxa_script_path]
        else:
            # JXA script to fetch calendar events
            start_ms = int(start.timestamp() * 1000) if start else "(new Date().getTime() - 3600000)"
            end_ms = int(end.timestamp() * 1000) if end else "(new Date().getTime() + 7 * 24 * 3600000)"
            jxa_script = """
        var app = Application('Calendar');
        var cals = app.calendars();
        var windowStart = new Date(%s);
        var windowEnd = new Date(%s);

        var events = [];
        for (var i = 0; i < cals.length; i++) {
            var cal = cals[i];
            var calEvents = cal.events.whose({
                _and: [
                    {startDate: {_greaterThanEquals: windowStart}},
                    {startDate: {_lessThanEquals: windowEnd}}
                ]
            })();

            for (var j = 0; j < calEvents.length; j++) {
                var evt = calEvents[j];
                events.push({
                    title: evt.summary(),
                    startDate: evt.startDate().toString(),
                    endDate: evt.endDate().toString(),
                    calendarTitle: cal.name(),
                    location: evt.location() || "",
                    notes: evt.description() || ""
                });
            }
        }
        JSON.stringify(events);
            """ % (start_ms, end_ms)
            command = ["osascript", "-l", "JavaScript", "-e", jxa_script]

        timeout_seconds = float(os.environ.get("MEETINGCTL_JXA_TIMEOUT_SECONDS", "30"))

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown JXA error"
                raise RuntimeError(
                    f"JXA script failed: {error_msg}. "
                    "Check calendar permissions. Run `meetingctl doctor` for diagnostics."
                )

            # Parse JSON output from JXA
            jxa_events = json.loads(result.stdout.strip())

            # Normalize to common schema
            normalized = []
            for event in jxa_events:
                normalized.append({
                    "title": event.get("title", ""),
                    "start": _normalize_datetime_string(str(event.get("startDate", ""))),
                    "end": _normalize_datetime_string(str(event.get("endDate", ""))),
                    "calendar_name": event.get("calendarTitle", ""),
                    "location": event.get("location", ""),
                    "notes": event.get("notes", ""),
                    "url": "",  # JXA doesn't expose URL easily
                })

            return normalized

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "JXA script timed out. Run `meetingctl doctor` for diagnostics."
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Failed to parse JXA output. Run `meetingctl doctor` for diagnostics."
            ) from exc

    def fetch_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, object]]:
        try:
            return self._loader(start=start, end=end)
        except TypeError:
            return self._loader()


def _run_eventkit_helper(
    helper_path: Path,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, object]]:
    if not helper_path.is_absolute():
        raise BackendUnavailableError(
            "EventKit helper path must be absolute for safety."
        )
    helper_path = helper_path.resolve()
    if not helper_path.exists():
        raise BackendUnavailableError(f"EventKit helper not found: {helper_path}")
    command = [sys.executable, str(helper_path)]
    if start:
        command.extend(["--start", start.isoformat()])
    if end:
        command.extend(["--end", end.isoformat()])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown EventKit helper error"
        raise BackendUnavailableError(
            f"EventKit helper failed: {error}. Run `meetingctl doctor` for diagnostics."
        )
    payload = json.loads(result.stdout.strip() or "[]")
    if not isinstance(payload, list):
        raise RuntimeError("Invalid EventKit helper output")
    normalized: list[dict[str, object]] = []
    for event in payload:
        if not isinstance(event, dict):
            continue
        copied = dict(event)
        copied["start"] = _normalize_datetime_string(str(event.get("start", "")))
        copied["end"] = _normalize_datetime_string(str(event.get("end", "")))
        normalized.append(copied)
    return normalized


def _default_eventkit_helper_path() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "eventkit_fetch.py"


def _normalize_datetime_string(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S %z",):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    return value
