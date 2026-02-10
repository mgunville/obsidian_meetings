from meetingctl.cli import build_parser


def test_parser_has_core_commands() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    for cmd in ["start", "stop", "status", "event", "doctor", "patch-note", "process-queue", "backfill"]:
        assert cmd in help_text
