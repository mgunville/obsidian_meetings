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


def test_audio_hijack_start_uses_configured_script(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_runner(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert check is True
        return subprocess.CompletedProcess(args, 0)

    script = tmp_path / "start.ahscript"
    script.write_text("// noop")
    monkeypatch.delenv("MEETINGCTL_RECORDING_DRY_RUN", raising=False)
    monkeypatch.setenv("MEETINGCTL_AUDIO_HIJACK_START_SCRIPT", str(script))
    recorder = AudioHijackRecorder(runner=fake_runner)
    recorder.start("Teams+Mic")

    assert len(calls) == 1
    assert calls[0][:3] == ["open", "-a", "Audio Hijack"]
    assert calls[0][-1] == str(script)


def test_audio_hijack_stop_uses_configured_script(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_runner(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert check is True
        return subprocess.CompletedProcess(args, 0)

    script = tmp_path / "stop.ahscript"
    script.write_text("// noop")
    monkeypatch.delenv("MEETINGCTL_RECORDING_DRY_RUN", raising=False)
    monkeypatch.setenv("MEETINGCTL_AUDIO_HIJACK_STOP_SCRIPT", str(script))
    recorder = AudioHijackRecorder(runner=fake_runner)
    recorder.stop("Zoom+Mic")

    assert len(calls) == 1
    assert calls[0][:3] == ["open", "-a", "Audio Hijack"]
    assert calls[0][-1] == str(script)
