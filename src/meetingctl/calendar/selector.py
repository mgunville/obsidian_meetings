from __future__ import annotations

from datetime import datetime, timedelta


def _event_key(event: dict[str, object]) -> tuple[datetime, str]:
    start = datetime.fromisoformat(str(event["start"]))
    title = str(event.get("title", ""))
    return (start, title)


def select_now_or_next(
    *, events: list[dict[str, object]], now: datetime, window_minutes: int
) -> dict[str, object] | None:
    ongoing: list[dict[str, object]] = []
    upcoming: list[dict[str, object]] = []
    window_end = now + timedelta(minutes=window_minutes)

    for event in events:
        start = datetime.fromisoformat(str(event["start"]))
        end = datetime.fromisoformat(str(event["end"]))
        if start <= now < end:
            ongoing.append(event)
        elif now < start <= window_end:
            upcoming.append(event)

    if ongoing:
        return sorted(ongoing, key=_event_key)[0]
    if upcoming:
        return sorted(upcoming, key=_event_key)[0]
    return None
