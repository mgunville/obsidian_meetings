from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import uuid

from scripts import diarization_catchup


def test_resolve_sidecar_output_path_maps_container_shared_root() -> None:
    resolved = diarization_catchup._resolve_sidecar_output_path(
        "/shared/diarization/jobs/example-job/transcript_diarized.txt"
    )

    expected = (
        Path(__file__).resolve().parents[1]
        / "shared_data"
        / "diarization"
        / "jobs"
        / "example-job"
        / "transcript_diarized.txt"
    ).resolve()
    assert resolved == expected


def test_run_copies_sidecar_outputs_from_container_manifest_paths(monkeypatch, tmp_path: Path) -> None:
    recordings = tmp_path / "audio"
    recordings.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    wav = recordings / "20260309-1000_Audio.wav"
    wav.write_text("wav")

    meeting_id = "m-testcopy123"
    note = vault / "Meetings" / f"2026-03-09 1000 - Demo - {meeting_id}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "\n".join(
            [
                "---",
                f'meeting_id: "{meeting_id}"',
                "---",
                f"- audio: {wav}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    artifact_dir = vault / "Meetings" / "_artifacts" / meeting_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / f"{meeting_id}.json").write_text('{"segments":[]}', encoding="utf-8")

    unique_dir = (
        Path(__file__).resolve().parents[1]
        / "shared_data"
        / "diarization"
        / "jobs"
        / f"test-catchup-copy-{uuid.uuid4().hex[:8]}"
    )
    unique_dir.mkdir(parents=True, exist_ok=True)
    side_txt = unique_dir / "transcript_diarized.txt"
    side_srt = unique_dir / "transcript_diarized.srt"
    side_json = unique_dir / "transcript_diarized.json"
    side_txt.write_text("hello", encoding="utf-8")
    side_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    side_json.write_text('{"segments":[{"text":"hello"}]}', encoding="utf-8")

    manifest = {
        "transcript_txt": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.txt",
        "transcript_srt": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.srt",
        "transcript_json": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.json",
    }

    def _runner(args, check=False, capture_output=True, text=True):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(manifest), stderr="")

    monkeypatch.setattr(diarization_catchup.subprocess, "run", _runner)

    args = diarization_catchup.build_parser().parse_args(
        [
            "--recordings-root",
            str(recordings),
            "--vault-path",
            str(vault),
            "--extensions",
            "wav",
            "--max-files",
            "1",
            "--prefer-existing-transcript-json",
            "--json",
        ]
    )
    try:
        payload = diarization_catchup.run(args)
    finally:
        shutil.rmtree(unique_dir, ignore_errors=True)

    assert payload["processed"] == 1
    assert payload["copied_to_artifacts"] == 1
    assert (artifact_dir / f"{meeting_id}.diarized.txt").read_text(encoding="utf-8") == "hello"
    assert (artifact_dir / f"{meeting_id}.diarized.srt").exists()
    assert (artifact_dir / f"{meeting_id}.diarized.json").exists()


def test_run_skips_recordings_shorter_than_minimum_duration(monkeypatch, tmp_path: Path) -> None:
    recordings = tmp_path / "audio"
    recordings.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    short_wav = recordings / "20260309-0900_Audio.wav"
    short_wav.write_text("wav")

    monkeypatch.setattr(diarization_catchup, "_audio_duration_seconds", lambda _path: 59.0)

    calls: list[list[str]] = []

    def _runner(args, check=False, capture_output=True, text=True):
        calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(diarization_catchup.subprocess, "run", _runner)

    args = diarization_catchup.build_parser().parse_args(
        [
            "--recordings-root",
            str(recordings),
            "--vault-path",
            str(vault),
            "--extensions",
            "wav",
            "--max-files",
            "1",
            "--min-duration-seconds",
            "60",
            "--json",
        ]
    )

    payload = diarization_catchup.run(args)

    assert payload["processed"] == 1
    assert payload["skipped"] == 1
    assert calls == []
    result = payload["results"][0]
    assert result["skipped"] is True
    assert result["audio_duration_seconds"] == 59.0
    assert "shorter than minimum duration" in result["error"]


def test_run_maps_source_audio_by_note_start_when_audio_reference_differs(monkeypatch, tmp_path: Path) -> None:
    recordings = tmp_path / "audio"
    recordings.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    source_audio = recordings / "20260304-1640_Audio.m4a"
    source_audio.write_text("m4a")

    meeting_id = "m-0ae0b59712"
    note = vault / "Meetings" / f"2026-03-04 1640 - Demo - {meeting_id}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "\n".join(
            [
                "---",
                f'meeting_id: "{meeting_id}"',
                'start: "2026-03-04T16:40:00-06:00"',
                "---",
                f"- audio: {recordings / (meeting_id + '.mp3')}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    artifact_dir = vault / "Meetings" / "_artifacts" / meeting_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    transcript_json = artifact_dir / f"{meeting_id}.json"
    transcript_json.write_text('{"segments":[]}', encoding="utf-8")

    monkeypatch.setattr(diarization_catchup, "_audio_duration_seconds", lambda _path: 2816.64)

    args = diarization_catchup.build_parser().parse_args(
        [
            "--recordings-root",
            str(recordings),
            "--vault-path",
            str(vault),
            "--extensions",
            "m4a",
            "--max-files",
            "1",
            "--prefer-existing-transcript-json",
            "--dry-run",
            "--json",
        ]
    )

    payload = diarization_catchup.run(args)

    assert payload["processed"] == 1
    result = payload["results"][0]
    assert result["meeting_id"] == meeting_id
    assert result["transcript_json_used"] == str(transcript_json.resolve())
    assert "--meeting-id" in result["command"]
    assert meeting_id in result["command"]


def test_run_creates_adhoc_note_for_unmapped_recording_and_copies_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    recordings = tmp_path / "audio"
    recordings.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    audio = recordings / "20260309-1000_Audio.m4a"
    audio.write_text("m4a")

    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setattr(diarization_catchup, "_audio_duration_seconds", lambda _path: 600.0)

    unique_dir = (
        Path(__file__).resolve().parents[1]
        / "shared_data"
        / "diarization"
        / "jobs"
        / f"test-catchup-adhoc-{uuid.uuid4().hex[:8]}"
    )
    unique_dir.mkdir(parents=True, exist_ok=True)
    side_txt = unique_dir / "transcript_diarized.txt"
    side_srt = unique_dir / "transcript_diarized.srt"
    side_json = unique_dir / "transcript_diarized.json"
    side_txt.write_text("hello", encoding="utf-8")
    side_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    side_json.write_text('{"segments":[{"speaker":"SPEAKER_00","text":"hello"}]}', encoding="utf-8")

    manifest = {
        "transcript_txt": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.txt",
        "transcript_srt": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.srt",
        "transcript_json": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.json",
    }

    def _runner(args, check=False, capture_output=True, text=True):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(manifest), stderr="")

    monkeypatch.setattr(diarization_catchup.subprocess, "run", _runner)

    args = diarization_catchup.build_parser().parse_args(
        [
            "--recordings-root",
            str(recordings),
            "--vault-path",
            str(vault),
            "--extensions",
            "m4a",
            "--max-files",
            "1",
            "--json",
        ]
    )

    try:
        payload = diarization_catchup.run(args)
    finally:
        shutil.rmtree(unique_dir, ignore_errors=True)

    assert payload["processed"] == 1
    assert payload["failed"] == 0
    assert payload["copied_to_artifacts"] == 1
    result = payload["results"][0]
    assert result["ok"] is True
    assert result["meeting_id"].startswith("m-")
    assert result["note_path"]
    note_path = Path(result["note_path"])
    assert note_path.exists()
    artifact_dir = vault / "Meetings" / "_artifacts" / result["meeting_id"]
    assert (artifact_dir / f"{result['meeting_id']}.diarized.txt").read_text(encoding="utf-8") == "hello"
    assert (artifact_dir / f"{result['meeting_id']}.diarized.srt").exists()
    assert (artifact_dir / f"{result['meeting_id']}.diarized.json").exists()
