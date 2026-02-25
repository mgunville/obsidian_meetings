from __future__ import annotations

from pathlib import Path

from meetingctl.note.template import render_meeting_note


def test_template_render_includes_required_frontmatter_keys() -> None:
    output = render_meeting_note(
        {
            "meeting_id": "m-123",
            "title": "Weekly Sync",
            "start_iso": "2026-02-08T10:00:00+00:00",
            "end_iso": "2026-02-08T11:00:00+00:00",
            "calendar_name": "Work",
            "platform": "teams",
            "join_url": "https://teams.microsoft.com/l/meetup-join/abc",
            "recording_wav_rel": "recordings/work/w.wav",
            "start_human": "10:00",
            "end_human": "11:00",
        }
    )

    for key in [
        "type: meeting",
        "meeting_id: \"m-123\"",
        "title: \"Weekly Sync\"",
        "start: \"2026-02-08T10:00:00+00:00\"",
        "end: \"2026-02-08T11:00:00+00:00\"",
        "platform: \"teams\"",
        "recording_wav: \"recordings/work/w.wav\"",
        "recording_mp3: \"\"",
        "transcript_status: \"pending\"",
        "summary_status: \"pending\"",
    ]:
        assert key in output


def test_template_render_contains_managed_sentinels() -> None:
    output = render_meeting_note(
        {
            "meeting_id": "m-123",
            "title": "Weekly Sync",
            "start_iso": "2026-02-08T10:00:00+00:00",
            "end_iso": "2026-02-08T11:00:00+00:00",
            "calendar_name": "Work",
            "platform": "teams",
            "join_url": "https://teams.microsoft.com/l/meetup-join/abc",
            "recording_wav_rel": "recordings/work/w.wav",
            "start_human": "10:00",
            "end_human": "11:00",
        }
    )
    for marker in [
        "<!-- MINUTES_START -->",
        "<!-- MINUTES_END -->",
        "<!-- DECISIONS_START -->",
        "<!-- DECISIONS_END -->",
        "<!-- ACTION_ITEMS_START -->",
        "<!-- ACTION_ITEMS_END -->",
        "<!-- TRANSCRIPT_START -->",
        "<!-- TRANSCRIPT_END -->",
        "<!-- REFERENCES_START -->",
        "<!-- REFERENCES_END -->",
    ]:
        assert marker in output


def test_template_render_uses_env_override_template(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "meeting.md"
    custom.write_text("title={{ title }}\nmeeting_id={{ meeting_id }}\n")
    monkeypatch.setenv("MEETINGCTL_NOTE_TEMPLATE_PATH", str(custom))
    output = render_meeting_note({"title": "X", "meeting_id": "m-1"})
    assert "title=X" in output
    assert "meeting_id=m-1" in output
