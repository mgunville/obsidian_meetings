from __future__ import annotations

from datetime import UTC, datetime

from meetingctl.calendar.backends import BackendUnavailableError, EventKitBackend, JXABackend
from meetingctl.calendar.selector import select_now_or_next


class CalendarResolutionError(RuntimeError):
    def __init__(self, *, backend: str, reason: str) -> None:
        self.backend = backend
        self.reason = reason
        self.hint = "Run `meetingctl doctor` and verify calendar permissions/backends."
        super().__init__(f"[{backend}] {reason}. {self.hint}")

    def to_payload(self) -> dict[str, object]:
        return {
            "error": self.reason,
            "backend": self.backend,
            "hint": self.hint,
        }


def _infer_join_url(event: dict[str, object]) -> str:
    candidates = [str(event.get("url", "")), str(event.get("location", "")), str(event.get("notes", ""))]
    for candidate in candidates:
        if "http" in candidate:
            start = candidate.find("http")
            return candidate[start:].split()[0]
    return ""


def _infer_platform(join_url: str) -> str:
    url = join_url.lower()
    if "teams.microsoft.com" in url:
        return "teams"
    if "zoom.us" in url:
        return "zoom"
    if "meet.google.com" in url:
        return "meet"
    if "webex.com" in url:
        return "webex"
    return "unknown"


def resolve_now_or_next_event(
    *,
    now: datetime | None = None,
    window_minutes: int,
    eventkit: EventKitBackend | None = None,
    jxa: JXABackend | None = None,
) -> dict[str, object]:
    now = now or datetime.now(UTC)
    eventkit = eventkit or EventKitBackend()
    jxa = jxa or JXABackend()

    try:
        events = eventkit.fetch_events()
        backend = "eventkit"
        fallback_used = False
    except BackendUnavailableError:
        try:
            events = jxa.fetch_events()
            backend = "jxa"
            fallback_used = True
        except Exception as exc:
            raise CalendarResolutionError(backend="jxa", reason=str(exc)) from exc
    except Exception as exc:
        raise CalendarResolutionError(backend="eventkit", reason=str(exc)) from exc

    selected = select_now_or_next(events=events, now=now, window_minutes=window_minutes)
    if selected is None:
        raise CalendarResolutionError(backend=backend, reason="No ongoing/upcoming event in window")

    join_url = _infer_join_url(selected)
    return {
        "title": selected.get("title"),
        "start": selected.get("start"),
        "end": selected.get("end"),
        "calendar_name": selected.get("calendar_name"),
        "join_url": join_url,
        "platform": _infer_platform(join_url),
        "backend": backend,
        "fallback_used": fallback_used,
    }
