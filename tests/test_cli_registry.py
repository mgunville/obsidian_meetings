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
    ]


def test_subcommand_help_renders() -> None:
    parser = build_parser()
    for command in registered_commands():
        subparser = parser._subparsers._group_actions[0].choices[command]  # type: ignore[attr-defined]
        assert "usage: meetingctl" in subparser.format_help()
