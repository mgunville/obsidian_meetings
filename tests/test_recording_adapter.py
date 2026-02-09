from __future__ import annotations

import subprocess

from meetingctl.recording import AudioHijackRecorder


def test_audio_hijack_start_calls_osascript(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_runner(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert check is True
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.delenv("MEETINGCTL_RECORDING_DRY_RUN", raising=False)
    recorder = AudioHijackRecorder(runner=fake_runner)
    recorder.start("Teams+Mic")

    assert len(calls) == 1
    assert calls[0][0] == "osascript"
    assert calls[0][1:3] == ["-l", "JavaScript"]
    assert "session.start()" in calls[0][-1]
    assert "Teams+Mic" in calls[0][-1]


def test_audio_hijack_stop_calls_osascript(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_runner(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert check is True
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.delenv("MEETINGCTL_RECORDING_DRY_RUN", raising=False)
    recorder = AudioHijackRecorder(runner=fake_runner)
    recorder.stop("Zoom+Mic")

    assert len(calls) == 1
    assert calls[0][0] == "osascript"
    assert calls[0][1:3] == ["-l", "JavaScript"]
    assert "session.stop()" in calls[0][-1]
    assert "Zoom+Mic" in calls[0][-1]


def test_audio_hijack_dry_run_skips_osascript(monkeypatch) -> None:
    invoked = False

    def fake_runner(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        nonlocal invoked
        invoked = True
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setenv("MEETINGCTL_RECORDING_DRY_RUN", "1")
    recorder = AudioHijackRecorder(runner=fake_runner)
    recorder.start("Teams+Mic")
    recorder.stop("Teams+Mic")

    assert invoked is False
