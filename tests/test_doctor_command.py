from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from meetingctl import cli
from meetingctl.doctor import run_doctor


def test_doctor_json_contract_success(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path / "recordings"))
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_UNAVAILABLE", "0")
    monkeypatch.setenv("MEETINGCTL_TEST_DOCTOR_ALL_OK", "1")
    monkeypatch.setattr("sys.argv", ["meetingctl", "doctor", "--json"])
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    expected = json.loads((Path(__file__).parent / "fixtures" / "doctor_ok.json").read_text())
    assert payload["ok"] is expected["ok"]
    assert payload["checks"][0]["name"] == "vault_path"


def test_doctor_failure_has_actionable_hints(monkeypatch) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.delenv("RECORDINGS_PATH", raising=False)
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_UNAVAILABLE", "1")
    monkeypatch.setenv("MEETINGCTL_JXA_UNAVAILABLE", "1")
    payload = run_doctor()
    assert payload["ok"] is False
    expected = json.loads((Path(__file__).parent / "fixtures" / "doctor_missing_paths.json").read_text())
    assert payload["checks"][:3] == expected["checks"]


def test_doctor_human_readable_output(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path / "recordings"))
    monkeypatch.setattr("sys.argv", ["meetingctl", "doctor"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "Doctor status:" in output
    assert "[PASS] vault_path" in output


@patch("meetingctl.doctor.EKEventStore")
def test_doctor_checks_eventkit_permissions(mock_ekstore_class: MagicMock, monkeypatch, tmp_path: Path) -> None:
    """Test that doctor checks real EventKit calendar permissions."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path))

    # Mock authorized status (3 = Authorized)
    mock_ekstore_class.authorizationStatusForEntityType_.return_value = 3

    payload = run_doctor()

    # Find the calendar permission check
    calendar_check = next((c for c in payload["checks"] if c["name"] == "calendar_permissions"), None)
    assert calendar_check is not None
    assert calendar_check["ok"] is True
    assert "authorized" in str(calendar_check["message"]).lower()


@patch("meetingctl.doctor.EKEventStore")
def test_doctor_detects_missing_calendar_permissions(mock_ekstore_class: MagicMock, monkeypatch, tmp_path: Path) -> None:
    """Test that doctor detects when calendar permissions are denied."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path))

    # Mock denied status (2 = Denied)
    mock_ekstore_class.authorizationStatusForEntityType_.return_value = 2

    payload = run_doctor()

    # Find the calendar permission check
    calendar_check = next((c for c in payload["checks"] if c["name"] == "calendar_permissions"), None)
    assert calendar_check is not None
    assert calendar_check["ok"] is False
    assert "denied" in str(calendar_check["message"]).lower() or "permission" in str(calendar_check["message"]).lower()
    assert "System Settings" in calendar_check["hint"]


@patch("meetingctl.doctor.subprocess.run")
def test_doctor_checks_audio_hijack(mock_run: MagicMock, monkeypatch, tmp_path: Path) -> None:
    """Test that doctor checks for Audio Hijack installation."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path))

    # Mock Audio Hijack binary found
    mock_run.return_value = MagicMock(returncode=0, stdout="/Applications/Audio Hijack.app")

    payload = run_doctor()

    # Find the audio hijack check
    ah_check = next((c for c in payload["checks"] if c["name"] == "audio_hijack"), None)
    assert ah_check is not None
    assert ah_check["ok"] is True


@patch("meetingctl.doctor.subprocess.run")
def test_doctor_detects_missing_audio_hijack(mock_run: MagicMock, monkeypatch, tmp_path: Path) -> None:
    """Test that doctor detects when Audio Hijack is not installed."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path))

    # Mock Audio Hijack binary not found
    mock_run.return_value = MagicMock(returncode=1, stdout="")

    payload = run_doctor()

    # Find the audio hijack check
    ah_check = next((c for c in payload["checks"] if c["name"] == "audio_hijack"), None)
    assert ah_check is not None
    assert ah_check["ok"] is False
    assert "Audio Hijack" in ah_check["message"]


@patch("meetingctl.doctor.os.access")
@patch("meetingctl.doctor.Path.exists")
def test_doctor_checks_eventkit_helper_presence(
    mock_exists: MagicMock, mock_access: MagicMock, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path))
    mock_exists.return_value = True
    mock_access.return_value = True

    payload = run_doctor()

    helper_check = next((c for c in payload["checks"] if c["name"] == "eventkit_helper"), None)
    assert helper_check is not None
    assert helper_check["ok"] is True
