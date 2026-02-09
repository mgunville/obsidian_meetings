#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import threading

try:
    from EventKit import EKEventStore, EKEntityTypeEvent
    from Foundation import NSDate
except Exception as exc:  # pragma: no cover - runtime integration path
    print(f"EventKit import failed: {exc}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    request_access = "--request-access" in sys.argv
    auth_status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
    if auth_status in (1, 2):
        print("Calendar permission denied or restricted.", file=sys.stderr)
        return 2

    store = EKEventStore.alloc().init()
    if request_access and auth_status == 0:
        done = threading.Event()
        result = {"granted": False}

        def _completion(granted: bool, _error: object) -> None:
            result["granted"] = bool(granted)
            done.set()

        store.requestAccessToEntityType_completion_(EKEntityTypeEvent, _completion)
        done.wait(timeout=10)
        if not result["granted"]:
            print("Calendar permission not granted.", file=sys.stderr)
            return 2

    now_ns = NSDate.date()
    start_date = now_ns.dateByAddingTimeInterval_(-3600)
    end_date = now_ns.dateByAddingTimeInterval_(7 * 24 * 3600)
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        start_date, end_date, None
    )
    events = store.eventsMatchingPredicate_(predicate)

    normalized: list[dict[str, object]] = []
    for event in events:
        calendar = event.calendar()
        url = event.URL()
        normalized.append(
            {
                "title": event.title() or "",
                "start": event.startDate().description() if event.startDate() else "",
                "end": event.endDate().description() if event.endDate() else "",
                "calendar_name": calendar.title() if calendar else "",
                "location": event.location() or "",
                "notes": event.notes() or "",
                "url": str(url) if url else "",
            }
        )

    print(json.dumps(normalized))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
