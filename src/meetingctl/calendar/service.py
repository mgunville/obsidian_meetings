from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re

from meetingctl.calendar.backends import (
    BackendUnavailableError,
    EventKitBackend,
    ICalBuddyBackend,
    JXABackend,
)
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
    icalbuddy: ICalBuddyBackend | None = None,
) -> dict[str, object]:
    now = now or datetime.now(UTC)
    eventkit = eventkit or EventKitBackend()
    jxa = jxa or JXABackend()
    icalbuddy = icalbuddy or ICalBuddyBackend()

    events, backend, fallback_used = _fetch_events(eventkit=eventkit, jxa=jxa, icalbuddy=icalbuddy)
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


def _fetch_events(
    *,
    eventkit: EventKitBackend,
    jxa: JXABackend,
    icalbuddy: ICalBuddyBackend,
) -> tuple[list[dict[str, object]], str, bool]:
    return _fetch_events_in_range(
        eventkit=eventkit,
        jxa=jxa,
        icalbuddy=icalbuddy,
        start=None,
        end=None,
    )


def _fetch_events_in_range(
    *,
    eventkit: EventKitBackend,
    jxa: JXABackend,
    icalbuddy: ICalBuddyBackend,
    start: datetime | None,
    end: datetime | None,
) -> tuple[list[dict[str, object]], str, bool]:
    eventkit_unavailable = False
    try:
        events = eventkit.fetch_events(start=start, end=end)
        backend = "eventkit"
        fallback_used = False
    except BackendUnavailableError:
        eventkit_unavailable = True
        events = []
        backend = "eventkit"
        fallback_used = False
    except Exception as exc:
        raise CalendarResolutionError(backend="eventkit", reason=str(exc)) from exc

    # EventKit unavailable or empty result: try JXA.
    if eventkit_unavailable or not events:
        try:
            jxa_events = jxa.fetch_events(start=start, end=end)
            if jxa_events:
                return jxa_events, "jxa", True
            if eventkit_unavailable:
                backend = "jxa"
        except Exception:
            if eventkit_unavailable:
                backend = "jxa"
                events = []

    # EventKit+JXA unavailable/empty: try icalBuddy.
    if eventkit_unavailable or backend == "jxa" or not events:
        try:
            ical_events = icalbuddy.fetch_events(start=start, end=end)
            if ical_events:
                return ical_events, "icalbuddy", True
            if eventkit_unavailable or backend == "jxa":
                backend = "icalbuddy"
        except Exception as exc:
            if eventkit_unavailable or backend == "jxa":
                raise CalendarResolutionError(backend="icalbuddy", reason=str(exc)) from exc
    return events, backend, fallback_used


def resolve_event_near_timestamp(
    *,
    at: datetime,
    window_minutes: int,
    eventkit: EventKitBackend | None = None,
    jxa: JXABackend | None = None,
    icalbuddy: ICalBuddyBackend | None = None,
) -> dict[str, object] | None:
    candidates = resolve_event_candidates_near_timestamp(
        at=at,
        window_minutes=window_minutes,
        max_candidates=25,
        eventkit=eventkit,
        jxa=jxa,
        icalbuddy=icalbuddy,
    )
    if not candidates:
        return None
    best_distance = float(candidates[0].get("match_distance_minutes", 0.0))
    best = [candidate for candidate in candidates if abs(float(candidate.get("match_distance_minutes", 0.0)) - best_distance) < 0.01]
    if len(best) != 1:
        return None
    return best[0]


def _ingest_match_stage(
    *,
    start_delta_minutes: float,
    forward_minutes: int,
    backward_minutes: int,
) -> int | None:
    # Priority order for live ingest calendar matching:
    # exact now -> forward(<=5) -> forward(<=10) -> backward(<=5/10/15).
    if abs(start_delta_minutes) < 0.01:
        return 0

    forward_limit = float(max(forward_minutes, 0))
    backward_limit = float(max(backward_minutes, 0))

    if start_delta_minutes > 0:
        if start_delta_minutes > forward_limit:
            return None
        if start_delta_minutes <= min(5.0, forward_limit):
            return 1
        if start_delta_minutes <= min(10.0, forward_limit):
            return 2
        return None

    backward_distance = abs(start_delta_minutes)
    if backward_distance > backward_limit:
        return None
    if backward_distance <= min(5.0, backward_limit):
        return 3
    if backward_distance <= min(10.0, backward_limit):
        return 4
    if backward_distance <= min(15.0, backward_limit):
        return 5
    return None


def resolve_event_candidates_near_now(
    *,
    now: datetime,
    forward_minutes: int,
    backward_minutes: int,
    max_candidates: int = 5,
    eventkit: EventKitBackend | None = None,
    jxa: JXABackend | None = None,
    icalbuddy: ICalBuddyBackend | None = None,
) -> list[dict[str, object]]:
    eventkit = eventkit or EventKitBackend()
    jxa = jxa or JXABackend()
    icalbuddy = icalbuddy or ICalBuddyBackend()
    forward_limit = max(forward_minutes, 0)
    backward_limit = max(backward_minutes, 0)

    window_start = now - timedelta(minutes=backward_limit)
    window_end = now + timedelta(minutes=forward_limit)
    events, backend, fallback_used = _fetch_events_in_range(
        eventkit=eventkit,
        jxa=jxa,
        icalbuddy=icalbuddy,
        start=window_start,
        end=window_end,
    )

    candidates: list[tuple[int, float, datetime, dict[str, object]]] = []
    for event in events:
        title = str(event.get("title", "")).strip().lower()
        if title.startswith("canceled:"):
            continue
        try:
            start = datetime.fromisoformat(str(event["start"]))
        except Exception:
            continue

        delta_minutes = (start - now).total_seconds() / 60.0
        stage = _ingest_match_stage(
            start_delta_minutes=delta_minutes,
            forward_minutes=forward_limit,
            backward_minutes=backward_limit,
        )
        if stage is None:
            continue
        candidates.append((stage, abs(delta_minutes), start, event))

    if not candidates:
        return []

    candidates.sort(key=lambda row: (row[0], row[1], row[2], str(row[3].get("title", ""))))
    payloads: list[dict[str, object]] = []
    for stage, distance, _, selected in candidates[: max(max_candidates, 1)]:
        join_url = _infer_join_url(selected)
        payloads.append(
            {
                "title": selected.get("title"),
                "start": selected.get("start"),
                "end": selected.get("end"),
                "calendar_name": selected.get("calendar_name"),
                "join_url": join_url,
                "platform": _infer_platform(join_url),
                "backend": backend,
                "fallback_used": fallback_used,
                "match_stage": stage,
                "match_distance_minutes": round(distance, 2),
            }
        )
    return payloads


def resolve_event_near_now(
    *,
    now: datetime,
    forward_minutes: int,
    backward_minutes: int,
    eventkit: EventKitBackend | None = None,
    jxa: JXABackend | None = None,
    icalbuddy: ICalBuddyBackend | None = None,
) -> dict[str, object] | None:
    candidates = resolve_event_candidates_near_now(
        now=now,
        forward_minutes=forward_minutes,
        backward_minutes=backward_minutes,
        max_candidates=25,
        eventkit=eventkit,
        jxa=jxa,
        icalbuddy=icalbuddy,
    )
    if not candidates:
        return None
    best_stage = int(candidates[0].get("match_stage", 999))
    stage_matches = [candidate for candidate in candidates if int(candidate.get("match_stage", 999)) == best_stage]
    if not stage_matches:
        return None
    best_distance = float(stage_matches[0].get("match_distance_minutes", 0.0))
    best = [
        candidate
        for candidate in stage_matches
        if abs(float(candidate.get("match_distance_minutes", 0.0)) - best_distance) < 0.01
    ]
    if len(best) != 1:
        return None
    return best[0]


def resolve_event_candidates_near_timestamp(
    *,
    at: datetime,
    window_minutes: int,
    max_candidates: int = 5,
    eventkit: EventKitBackend | None = None,
    jxa: JXABackend | None = None,
    icalbuddy: ICalBuddyBackend | None = None,
) -> list[dict[str, object]]:
    eventkit = eventkit or EventKitBackend()
    jxa = jxa or JXABackend()
    icalbuddy = icalbuddy or ICalBuddyBackend()
    local_at = at.astimezone()
    day_start = local_at.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    events, backend, fallback_used = _fetch_events_in_range(
        eventkit=eventkit,
        jxa=jxa,
        icalbuddy=icalbuddy,
        start=day_start,
        end=day_end,
    )

    candidates: list[tuple[float, dict[str, object], datetime, datetime]] = []
    for event in events:
        try:
            start = datetime.fromisoformat(str(event["start"]))
            end = datetime.fromisoformat(str(event["end"]))
        except Exception:
            continue
        # Treat end as exclusive to avoid ambiguity when one meeting ends exactly
        # as another starts (prefer the newly-started meeting at boundary times).
        if start <= at < end:
            distance_minutes = 0.0
        else:
            distance_minutes = abs((start - at).total_seconds()) / 60.0
        if distance_minutes <= float(max(window_minutes, 0)):
            candidates.append((distance_minutes, event, start, end))

    if not candidates:
        return []

    candidates.sort(key=lambda row: (row[0], row[2], str(row[1].get("title", ""))))
    payloads: list[dict[str, object]] = []
    for distance, selected, _, _ in candidates[: max(max_candidates, 1)]:
        join_url = _infer_join_url(selected)
        payloads.append(
            {
                "title": selected.get("title"),
                "start": selected.get("start"),
                "end": selected.get("end"),
                "calendar_name": selected.get("calendar_name"),
                "join_url": join_url,
                "platform": _infer_platform(join_url),
                "backend": backend,
                "fallback_used": fallback_used,
                "match_distance_minutes": round(distance, 2),
            }
        )
    return payloads
