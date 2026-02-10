from __future__ import annotations

from datetime import UTC, datetime
import re

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
    urls: list[str] = []
    for candidate in candidates:
        urls.extend(re.findall(r"https?://[^\s<>\"']+", candidate))

    if not urls:
        return ""

    preferred_domains = (
        "teams.microsoft.com",
        "zoom.us",
        "meet.google.com",
        "webex.com",
    )
    for domain in preferred_domains:
        for url in urls:
            if domain in url.lower():
                return url
    return urls[0]


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

    events, backend, fallback_used = _fetch_events(eventkit=eventkit, jxa=jxa)
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


def _fetch_events(*, eventkit: EventKitBackend, jxa: JXABackend) -> tuple[list[dict[str, object]], str, bool]:
    try:
        events = eventkit.fetch_events()
        backend = "eventkit"
        fallback_used = False
        # Some runtimes return an empty EventKit result despite calendar data being
        # available via JXA. Prefer JXA only when it can provide at least one event.
        if not events:
            try:
                jxa_events = jxa.fetch_events()
                if jxa_events:
                    events = jxa_events
                    backend = "jxa"
                    fallback_used = True
            except Exception:
                # Keep EventKit empty result semantics when JXA is unavailable/erroring.
                pass
    except BackendUnavailableError:
        try:
            events = jxa.fetch_events()
            backend = "jxa"
            fallback_used = True
        except Exception as exc:
            raise CalendarResolutionError(backend="jxa", reason=str(exc)) from exc
    except Exception as exc:
        raise CalendarResolutionError(backend="eventkit", reason=str(exc)) from exc
    return events, backend, fallback_used


def resolve_event_near_timestamp(
    *,
    at: datetime,
    window_minutes: int,
    eventkit: EventKitBackend | None = None,
    jxa: JXABackend | None = None,
) -> dict[str, object] | None:
    eventkit = eventkit or EventKitBackend()
    jxa = jxa or JXABackend()
    events, backend, fallback_used = _fetch_events(eventkit=eventkit, jxa=jxa)

    candidates: list[tuple[float, dict[str, object], datetime, datetime]] = []
    for event in events:
        try:
            start = datetime.fromisoformat(str(event["start"]))
            end = datetime.fromisoformat(str(event["end"]))
        except Exception:
            continue
        if start <= at <= end:
            distance_minutes = 0.0
        else:
            distance_minutes = abs((start - at).total_seconds()) / 60.0
        if distance_minutes <= float(max(window_minutes, 0)):
            candidates.append((distance_minutes, event, start, end))

    if not candidates:
        return None

    candidates.sort(key=lambda row: (row[0], row[2], str(row[1].get("title", ""))))
    best_distance = candidates[0][0]
    best = [candidate for candidate in candidates if abs(candidate[0] - best_distance) < 0.01]
    if len(best) != 1:
        return None

    _, selected, _, _ = best[0]
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
        "match_distance_minutes": round(best_distance, 2),
    }
