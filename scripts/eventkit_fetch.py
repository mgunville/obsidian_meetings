#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta
import sys
import threading
import time
from zoneinfo import ZoneInfo

try:
    from EventKit import EKEventStore, EKEntityTypeEvent
    from Foundation import NSDate
except Exception as exc:  # pragma: no cover - runtime integration path
    print(f"EventKit import failed: {exc}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    request_access = "--request-access" in sys.argv
    today_only = "--today" in sys.argv
    start_arg = ""
    end_arg = ""
    if "--start" in sys.argv:
        idx = sys.argv.index("--start")
        if idx + 1 < len(sys.argv):
            start_arg = sys.argv[idx + 1]
    if "--end" in sys.argv:
        idx = sys.argv.index("--end")
        if idx + 1 < len(sys.argv):
            end_arg = sys.argv[idx + 1]
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
        current_status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
        # In some runtimes the callback may not fire reliably without a full app run loop.
        # Poll status briefly so we do not misreport denied access when authorization succeeded.
        if current_status == 0 and not done.is_set():
            for _ in range(10):
                time.sleep(0.3)
                current_status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
                if current_status != 0:
                    break
        if not result["granted"] and current_status != 3:
            print("Calendar permission not granted.", file=sys.stderr)
            return 2

    now_ns = NSDate.date()
    if start_arg and end_arg:
        try:
            start_dt = datetime.fromisoformat(start_arg.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_arg.replace("Z", "+00:00"))
        except ValueError:
            print("Invalid --start/--end. Expected ISO-8601 datetime.", file=sys.stderr)
            return 2
        start_date = NSDate.dateWithTimeIntervalSince1970_(start_dt.timestamp())
        end_date = NSDate.dateWithTimeIntervalSince1970_(end_dt.timestamp())
    elif today_only:
        local_tz = datetime.now().astimezone().tzinfo or ZoneInfo("UTC")
        local_now = datetime.now(local_tz)
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_end = local_start + timedelta(days=1)
        start_date = NSDate.dateWithTimeIntervalSince1970_(local_start.timestamp())
        end_date = NSDate.dateWithTimeIntervalSince1970_(local_end.timestamp())
    else:
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
