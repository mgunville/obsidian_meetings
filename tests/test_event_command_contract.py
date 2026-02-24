from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


def test_event_command_json_contract(monkeypatch, capsys) -> None:
    monkeypatch.setenv("MEETINGCTL_NOW_ISO", "2026-02-08T10:05:00+00:00")
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_UNAVAILABLE", "0")
    monkeypatch.setenv(
        "MEETINGCTL_EVENTKIT_EVENTS_JSON",
        json.dumps(
            [
                {
                    "title": "Weekly Sync",
                    "start": "2026-02-08T10:00:00+00:00",
                    "end": "2026-02-08T10:30:00+00:00",
                    "location": "https://teams.microsoft.com/l/meetup-join/abc",
                    "calendar_name": "Work",
                }
            ]
        ),
    )
    monkeypatch.setattr("sys.argv", ["meetingctl", "event", "--now-or-next", "5", "--json"])
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    expected = json.loads((Path(__file__).parent / "fixtures" / "event_now_or_next.json").read_text())
    assert payload == expected


def test_event_command_error_is_backend_aware(monkeypatch, capsys) -> None:
    monkeypatch.setenv("MEETINGCTL_NOW_ISO", "2026-02-08T10:05:00+00:00")
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_UNAVAILABLE", "1")
    monkeypatch.setenv("MEETINGCTL_JXA_UNAVAILABLE", "1")
    monkeypatch.setenv("MEETINGCTL_ICALBUDDY_UNAVAILABLE", "1")
    monkeypatch.setattr("sys.argv", ["meetingctl", "event", "--json"])
    assert cli.main() == 2
    payload = json.loads(capsys.readouterr().out)
    expected = json.loads(
        (Path(__file__).parent / "fixtures" / "event_error_jxa_unavailable.json").read_text()
    )
    assert payload == expected
