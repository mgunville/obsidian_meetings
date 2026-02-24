from meetingctl.cli import build_parser, registered_commands


def test_registered_commands_are_stable() -> None:
    assert registered_commands() == [
        "start",
        "stop",
        "status",
        "event",
        "doctor",
        "patch-note",
        "process-queue",
        "backfill",
        "ingest-watch",
        "audit-notes",
    ]


def test_subcommand_help_renders() -> None:
    parser = build_parser()
    for command in registered_commands():
        subparser = parser._subparsers._group_actions[0].choices[command]  # type: ignore[attr-defined]
        assert "usage: meetingctl" in subparser.format_help()


def test_env_defaults_apply_to_backfill_and_ingest(monkeypatch) -> None:
    monkeypatch.setenv("MEETINGCTL_MATCH_WINDOW_MINUTES", "30")
    monkeypatch.setenv("MEETINGCTL_INGEST_MIN_AGE_SECONDS", "45")
    monkeypatch.setenv("MEETINGCTL_BACKFILL_EXTENSIONS", "wav,m4a")
    monkeypatch.setenv("MEETINGCTL_INGEST_EXTENSIONS", "wav,m4a")
    parser = build_parser()

    backfill_args = parser.parse_args(["backfill"])
    assert backfill_args.window_minutes == 30
    assert backfill_args.extensions == "wav,m4a"

    ingest_args = parser.parse_args(["ingest-watch"])
    assert ingest_args.window_minutes == 30
    assert ingest_args.min_age_seconds == 45
    assert ingest_args.extensions == "wav,m4a"
