from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from collections import Counter
from typing import Any

import torch
import whisperx


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return cleaned.strip("-") or "job"


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _format_seconds(total_seconds: float | int | None) -> str:
    if total_seconds is None:
        return "00:00:00"
    seconds_int = max(int(total_seconds), 0)
    hours = seconds_int // 3600
    minutes = (seconds_int % 3600) // 60
    seconds = seconds_int % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _coerce_float(value: Any, fallback: float | None = None) -> float | None:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_int(value: Any, fallback: int | None = None) -> int | None:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_speaker(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNKNOWN"
    return text


def _append_token(text: str, token: str) -> str:
    raw = str(token or "")
    if not raw:
        return text
    stripped = raw.strip()
    if not stripped:
        return text
    if not text:
        return stripped
    if raw.startswith(" "):
        return f"{text}{raw}"
    if re.match(r"^[,.;:!?%)}\]]", stripped):
        return f"{text}{stripped}"
    if stripped.startswith("'"):
        return f"{text}{stripped}"
    return f"{text} {stripped}"


def _build_turn_lines(
    result: dict[str, Any], *, max_gap_seconds: float, max_turn_duration_seconds: float
) -> list[str]:
    items: list[dict[str, Any]] = []
    for segment in result.get("segments", []) or []:
        if not isinstance(segment, dict):
            continue
        seg_speaker = _normalize_speaker(segment.get("speaker"))
        seg_start = _coerce_float(segment.get("start"))
        seg_end = _coerce_float(segment.get("end"), seg_start)
        words = segment.get("words")
        if isinstance(words, list) and words:
            for word in words:
                if not isinstance(word, dict):
                    continue
                token = str(word.get("word") or word.get("text") or "")
                if not token.strip():
                    continue
                speaker = _normalize_speaker(word.get("speaker") or seg_speaker)
                start = _coerce_float(word.get("start"), seg_start)
                end = _coerce_float(word.get("end"), seg_end if seg_end is not None else start)
                if start is None:
                    continue
                if end is None or end < start:
                    end = start
                items.append({"speaker": speaker, "start": start, "end": end, "token": token})
            continue

        text = str(segment.get("text") or "").strip()
        if not text or seg_start is None:
            continue
        items.append(
            {
                "speaker": seg_speaker,
                "start": seg_start,
                "end": seg_end if seg_end is not None else seg_start,
                "token": text,
            }
        )

    # Only switch to turn formatting if at least one non-UNKNOWN label exists.
    if not items or not any(item["speaker"] != "UNKNOWN" for item in items):
        return []

    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    max_gap = max(max_gap_seconds, 0.0)
    for item in items:
        speaker = str(item["speaker"])
        start = float(item["start"])
        end = float(item["end"])
        token = str(item["token"])

        if current is None:
            current = {"speaker": speaker, "start": start, "end": end, "text": ""}
            current["text"] = _append_token(str(current["text"]), token)
            continue

        gap = start - float(current["end"])
        speaker_changed = speaker != str(current["speaker"])
        duration_exceeded = (
            max_turn_duration_seconds > 0
            and (end - float(current["start"])) > max_turn_duration_seconds
        )
        if speaker_changed or gap > max_gap or duration_exceeded:
            text = str(current.get("text", "")).strip()
            if text:
                turns.append(current)
            current = {"speaker": speaker, "start": start, "end": end, "text": ""}

        current["end"] = max(float(current["end"]), end)
        current["text"] = _append_token(str(current["text"]), token)

    if current is not None:
        text = str(current.get("text", "")).strip()
        if text:
            turns.append(current)

    lines: list[str] = []
    for turn in turns:
        start = _format_seconds(_coerce_float(turn.get("start")))
        end = _format_seconds(_coerce_float(turn.get("end"), _coerce_float(turn.get("start"))))
        speaker = _normalize_speaker(turn.get("speaker"))
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{start}-{end}] {speaker}: {text}")
    return lines


def _build_txt_lines(
    result: dict[str, Any], *, max_gap_seconds: float, max_turn_duration_seconds: float
) -> list[str]:
    lines = _build_turn_lines(
        result,
        max_gap_seconds=max_gap_seconds,
        max_turn_duration_seconds=max_turn_duration_seconds,
    )
    if lines:
        return lines

    lines: list[str] = []
    for segment in result.get("segments", []) or []:
        if not isinstance(segment, dict):
            continue
        speaker = str(segment.get("speaker") or "UNKNOWN")
        start = _format_seconds(segment.get("start"))
        end = _format_seconds(segment.get("end"))
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{start}-{end}] {speaker}: {text}")
    return lines


def _build_srt_lines(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    idx = 1
    for segment in result.get("segments", []) or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        speaker = str(segment.get("speaker") or "UNKNOWN")
        start_raw = float(segment.get("start") or 0.0)
        end_raw = float(segment.get("end") or start_raw)
        start_h = int(start_raw // 3600)
        start_m = int((start_raw % 3600) // 60)
        start_s = int(start_raw % 60)
        start_ms = int((start_raw - int(start_raw)) * 1000)

        end_h = int(end_raw // 3600)
        end_m = int((end_raw % 3600) // 60)
        end_s = int(end_raw % 60)
        end_ms = int((end_raw - int(end_raw)) * 1000)

        lines.append(str(idx))
        lines.append(
            f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> "
            f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}"
        )
        lines.append(f"{speaker}: {text}")
        lines.append("")
        idx += 1
    return lines


def _resolve_token() -> str:
    for name in ("PYANNOTE_AUTH_TOKEN", "HF_TOKEN", "HUGGINGFACE_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value.startswith("<concealed by 1Password>"):
            continue
        if value:
            return value
    for name in (
        "MEETINGCTL_HF_TOKEN_FILE",
        "HUGGINGFACE_TOKEN_FILE",
        "HF_TOKEN_FILE",
        "PYANNOTE_AUTH_TOKEN_FILE",
    ):
        raw_path = os.environ.get(name, "").strip()
        if not raw_path:
            continue
        token_path = Path(raw_path).expanduser()
        if not token_path.is_file():
            continue
        try:
            token = token_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if token.startswith("<concealed by 1Password>"):
            continue
        if token:
            return token
    return ""


def _env_truthy(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _configure_offline_mode(enabled: bool) -> None:
    if not enabled:
        return
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")


def _configure_hf_client() -> None:
    # Avoid xet CAS endpoints by default on managed networks where TLS interception
    # breaks rustls verification for xethub hosts.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    if not (
        _env_truthy("MEETINGCTL_DIARIZATION_INSECURE_SSL")
        or _env_truthy("MEETINGCTL_INSECURE_SSL")
    ):
        return
    # huggingface_hub>=1 uses httpx factories.
    try:
        import httpx
        from huggingface_hub import set_async_client_factory, set_client_factory

        def _client_factory() -> Any:
            return httpx.Client(verify=False, timeout=httpx.Timeout(60.0, connect=30.0))

        def _async_client_factory() -> Any:
            return httpx.AsyncClient(verify=False, timeout=httpx.Timeout(60.0, connect=30.0))

        set_client_factory(_client_factory)
        set_async_client_factory(_async_client_factory)
    except Exception:
        pass

    # huggingface_hub<1 uses requests; patch Session.request in insecure mode.
    try:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        original_request = requests.sessions.Session.request

        def _insecure_request(self: Any, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
            kwargs["verify"] = False
            return original_request(self, method, url, *args, **kwargs)

        requests.sessions.Session.request = _insecure_request
    except Exception:
        pass


def _load_align_model(result: dict[str, Any], device: str) -> tuple[Any, dict[str, Any]] | tuple[None, None]:
    language = str(result.get("language") or "").strip()
    if not language:
        return None, None
    try:
        model, metadata = whisperx.load_align_model(language_code=language, device=device)
    except Exception:
        return None, None
    return model, metadata


def _diarization_model_list(raw: str) -> list[str]:
    defaults = "pyannote/speaker-diarization-3.1,pyannote/speaker-diarization"
    value = (raw or defaults).strip()
    models: list[str] = []
    for part in value.split(","):
        model = part.strip()
        if not model or model in models:
            continue
        models.append(model)
    return models or defaults.split(",")


def _resolve_cached_model_snapshot(model_name: str) -> Path | None:
    if not model_name:
        return None
    if "/" not in model_name:
        path = Path(model_name).expanduser()
        return path if path.exists() else None

    roots: list[Path] = []
    for env_name in ("HF_HOME", "WHISPERX_DOWNLOAD_ROOT"):
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path not in roots:
            roots.append(path)
    default_root = Path.home() / ".cache" / "huggingface"
    if default_root not in roots:
        roots.append(default_root)

    repo_dir_name = f"models--{model_name.replace('/', '--')}"
    for root in roots:
        hub_root = root / "hub" if (root / "hub").exists() else root
        model_root = hub_root / repo_dir_name
        if not model_root.exists():
            continue

        refs_main = model_root / "refs" / "main"
        if refs_main.exists():
            try:
                ref = refs_main.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                ref = ""
            if ref:
                candidate = model_root / "snapshots" / ref
                if (candidate / "config.yaml").exists():
                    return candidate

        snapshots = model_root / "snapshots"
        if not snapshots.exists():
            continue
        for candidate in sorted(snapshots.iterdir(), reverse=True):
            if candidate.is_dir() and (candidate / "config.yaml").exists():
                return candidate
    return None


def _cluster_embeddings(
    embeddings: Any,
    *,
    min_speakers: int | None,
    max_speakers: int | None,
    distance_threshold: float,
) -> Any:
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import silhouette_score

    sample_count = len(embeddings)
    if sample_count <= 1:
        return [0] * sample_count

    def fit_labels(*, n_clusters: int | None = None, threshold: float | None = None) -> Any:
        kwargs: dict[str, Any] = {"linkage": "average"}
        if n_clusters is None:
            kwargs["n_clusters"] = None
            kwargs["distance_threshold"] = max(float(threshold or 0.01), 0.01)
        else:
            kwargs["n_clusters"] = max(1, min(int(n_clusters), sample_count))

        try:
            clusterer = AgglomerativeClustering(metric="cosine", **kwargs)
        except TypeError:
            # Older sklearn uses `affinity` instead of `metric`.
            clusterer = AgglomerativeClustering(affinity="cosine", **kwargs)
        return clusterer.fit_predict(embeddings)

    fixed_n: int | None = None
    if min_speakers is not None and max_speakers is not None and min_speakers == max_speakers:
        fixed_n = max(1, min(min_speakers, sample_count))
    elif min_speakers is not None and max_speakers is not None and min_speakers > max_speakers:
        fixed_n = max(1, min(max_speakers, sample_count))
    elif min_speakers is not None:
        fixed_n = max(1, min(min_speakers, sample_count))
    elif max_speakers is not None:
        fixed_n = max(1, min(max_speakers, sample_count))

    if fixed_n is not None:
        return fit_labels(n_clusters=fixed_n)

    auto_cluster_raw = os.environ.get("WHISPERX_DIARIZATION_AUTO_CLUSTER", "1").strip().lower()
    auto_cluster = auto_cluster_raw not in {"0", "false", "no", "off"}
    if auto_cluster and sample_count >= 12:
        auto_min = _coerce_int(os.environ.get("WHISPERX_DIARIZATION_AUTO_MIN_SPEAKERS"), 2) or 2
        auto_max_default = _coerce_int(os.environ.get("WHISPERX_DIARIZATION_AUTO_MAX_SPEAKERS"), 6) or 6
        auto_max = min(auto_max_default, sample_count)
        if min_speakers is not None:
            auto_min = max(auto_min, min_speakers)
        if max_speakers is not None:
            auto_max = min(auto_max, max_speakers)
        auto_min = max(2, min(auto_min, auto_max))

        min_cluster_fraction = _coerce_float(
            os.environ.get("WHISPERX_DIARIZATION_AUTO_MIN_CLUSTER_FRACTION"),
            0.06,
        ) or 0.06
        min_cluster_windows = _coerce_int(
            os.environ.get("WHISPERX_DIARIZATION_AUTO_MIN_CLUSTER_WINDOWS"),
            3,
        ) or 3
        min_silhouette = _coerce_float(os.environ.get("WHISPERX_DIARIZATION_AUTO_MIN_SILHOUETTE"), 0.12) or 0.12
        score_sample_max = _coerce_int(
            os.environ.get("WHISPERX_DIARIZATION_AUTO_SCORE_SAMPLE_MAX"),
            1000,
        ) or 1000
        score_sample_max = max(score_sample_max, 100)

        score_indices: Any | None = None
        score_embeddings = np.asarray(embeddings, dtype=np.float32)
        if sample_count > score_sample_max:
            score_indices = np.linspace(0, sample_count - 1, num=score_sample_max, dtype=int)
            score_embeddings = score_embeddings[score_indices]

        best_labels: Any | None = None
        best_silhouette = -1.0
        best_score = -1.0
        for k in range(auto_min, auto_max + 1):
            labels = fit_labels(n_clusters=k)
            unique_labels, counts = np.unique(labels, return_counts=True)
            if unique_labels.size <= 1:
                continue
            if int(np.min(counts)) < min_cluster_windows:
                continue
            if float(np.min(counts)) / float(sample_count) < min_cluster_fraction:
                continue
            score_labels = labels[score_indices] if score_indices is not None else labels
            if len(set(int(x) for x in score_labels.tolist())) <= 1:
                continue
            try:
                sil = float(silhouette_score(score_embeddings, score_labels, metric="cosine"))
            except Exception:
                continue

            # Light complexity penalty to prefer simpler partitions when quality is similar.
            score = sil - (0.01 * float(k - 1))
            if score > best_score:
                best_score = score
                best_silhouette = sil
                best_labels = labels

        if best_labels is not None and best_silhouette >= min_silhouette:
            return best_labels

    return fit_labels(n_clusters=None, threshold=distance_threshold)


def _assign_segment_speakers_from_embeddings(
    *,
    audio: Any,
    result: dict[str, Any],
    min_speakers: int | None,
    max_speakers: int | None,
) -> dict[str, Any]:
    import numpy as np
    import torchaudio

    segments = result.get("segments", []) or []
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("No transcript segments available for embedding-based diarization")

    distance_threshold = _coerce_float(os.environ.get("WHISPERX_DIARIZATION_SEGMENT_CLUSTER_DISTANCE"), 0.08)
    if distance_threshold is None:
        distance_threshold = 0.08

    mfcc = torchaudio.transforms.MFCC(
        sample_rate=16000,
        n_mfcc=24,
        melkwargs={
            "n_fft": 400,
            "hop_length": 160,
            "n_mels": 48,
            "center": False,
        },
    )

    sample_rate = 16000
    audio_array = np.asarray(audio, dtype=np.float32)
    if audio_array.size == 0:
        raise RuntimeError("Empty audio array for fallback diarization")

    window_seconds = _coerce_float(os.environ.get("WHISPERX_DIARIZATION_WINDOW_SECONDS"), 1.6) or 1.6
    hop_seconds = _coerce_float(os.environ.get("WHISPERX_DIARIZATION_HOP_SECONDS"), 0.8) or 0.8
    smoothing_span = _coerce_int(os.environ.get("WHISPERX_DIARIZATION_LABEL_SMOOTH_SPAN"), 5) or 5
    if smoothing_span < 1:
        smoothing_span = 1
    if smoothing_span % 2 == 0:
        smoothing_span += 1
    window_samples = max(int(window_seconds * sample_rate), int(0.8 * sample_rate))
    hop_samples = max(int(hop_seconds * sample_rate), int(0.4 * sample_rate))
    energy_quantile = _coerce_float(os.environ.get("WHISPERX_DIARIZATION_ENERGY_QUANTILE"), 0.35) or 0.35
    energy_floor = _coerce_float(os.environ.get("WHISPERX_DIARIZATION_ENERGY_FLOOR"), 0.004) or 0.004

    candidate_windows: list[dict[str, Any]] = []
    rms_values: list[float] = []
    for start_idx in range(0, max(audio_array.size - window_samples + 1, 1), hop_samples):
        end_idx = min(start_idx + window_samples, audio_array.size)
        if end_idx <= start_idx:
            continue
        chunk = audio_array[start_idx:end_idx]
        if chunk.size < int(0.4 * sample_rate):
            continue
        rms = float(np.sqrt(np.mean(chunk**2) + 1e-12))
        candidate_windows.append(
            {
                "start": start_idx / sample_rate,
                "end": end_idx / sample_rate,
                "chunk": chunk,
                "rms": rms,
            }
        )
        rms_values.append(rms)

    if not candidate_windows:
        raise RuntimeError("No candidate windows extracted for fallback diarization")

    dynamic_threshold = float(np.quantile(np.asarray(rms_values, dtype=np.float32), min(max(energy_quantile, 0.0), 1.0)))
    threshold = max(dynamic_threshold, energy_floor)
    active_windows = [win for win in candidate_windows if float(win["rms"]) >= threshold]
    if len(active_windows) < 2:
        active_windows = sorted(candidate_windows, key=lambda x: float(x["rms"]), reverse=True)[: max(2, len(candidate_windows))]

    embeddings: list[np.ndarray] = []
    for win in active_windows:
        waveform = torch.tensor(win["chunk"], dtype=torch.float32).unsqueeze(0)
        coeffs = mfcc(waveform).squeeze(0).detach().cpu().numpy()
        if coeffs.ndim != 2 or coeffs.shape[1] == 0:
            continue
        mean = np.mean(coeffs, axis=1)
        std = np.std(coeffs, axis=1)
        delta_1 = np.diff(coeffs, axis=1)
        delta_2 = np.diff(delta_1, axis=1) if delta_1.shape[1] > 1 else delta_1
        delta_1_mean = np.mean(np.abs(delta_1), axis=1)
        delta_2_mean = np.mean(np.abs(delta_2), axis=1)

        chunk = np.asarray(win["chunk"], dtype=np.float32)
        zcr = float(np.mean(np.abs(np.diff(np.sign(chunk)))) / 2.0)
        spectrum = np.abs(np.fft.rfft(chunk))
        freqs = np.fft.rfftfreq(chunk.size, d=1.0 / sample_rate)
        centroid = float(np.sum(freqs * spectrum) / max(np.sum(spectrum), 1e-9))
        centroid_norm = centroid / (sample_rate / 2.0)
        prosody = np.asarray([np.log(max(float(win["rms"]), 1e-8)), zcr, centroid_norm], dtype=np.float32)

        emb = np.concatenate([mean, std, delta_1_mean, delta_2_mean, prosody], axis=0)
        norm = float(np.linalg.norm(emb))
        if norm > 0:
            emb = emb / norm
        embeddings.append(emb)

    if len(embeddings) == 0:
        raise RuntimeError("Unable to extract MFCC embeddings for fallback diarization")

    emb_matrix = np.vstack(embeddings)
    labels = _cluster_embeddings(
        emb_matrix,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        distance_threshold=distance_threshold,
    )
    labels = [int(x) for x in list(labels)]

    if smoothing_span > 1 and len(labels) >= smoothing_span:
        radius = smoothing_span // 2
        smoothed_labels: list[int] = []
        for idx, raw_label in enumerate(labels):
            start = max(0, idx - radius)
            end = min(len(labels), idx + radius + 1)
            window = labels[start:end]
            counts: dict[int, int] = {}
            for item in window:
                counts[item] = counts.get(item, 0) + 1
            best_label = raw_label
            best_count = -1
            for item, count in counts.items():
                if count > best_count:
                    best_label = item
                    best_count = count
                elif count == best_count and item == raw_label:
                    best_label = item
            smoothed_labels.append(best_label)
        labels = smoothed_labels

    label_map: dict[Any, str] = {}
    for raw_label in labels:
        if raw_label not in label_map:
            label_map[raw_label] = f"SPEAKER_{len(label_map):02d}"

    diar_windows: list[dict[str, Any]] = []
    for win, raw_label in zip(active_windows, labels):
        diar_windows.append(
            {
                "start": float(win["start"]),
                "end": float(win["end"]),
                "speaker": label_map[raw_label],
            }
        )
    diar_windows.sort(key=lambda x: (float(x["start"]), float(x["end"])))

    merged_windows: list[dict[str, Any]] = []
    max_merge_gap = hop_seconds * 1.25
    for win in diar_windows:
        if not merged_windows:
            merged_windows.append(win.copy())
            continue
        prev = merged_windows[-1]
        if prev["speaker"] == win["speaker"] and float(win["start"]) - float(prev["end"]) <= max_merge_gap:
            prev["end"] = max(float(prev["end"]), float(win["end"]))
        else:
            merged_windows.append(win.copy())

    def speaker_for_interval(start: float, end: float) -> str:
        best_overlap = 0.0
        best_speaker = "UNKNOWN"
        for win in merged_windows:
            overlap = min(end, float(win["end"])) - max(start, float(win["start"]))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = str(win["speaker"])
        if best_overlap > 0:
            return best_speaker
        center = (start + end) / 2.0
        nearest = min(merged_windows, key=lambda x: abs(center - ((float(x["start"]) + float(x["end"])) / 2.0)))
        return str(nearest["speaker"])

    segments_for_cleanup: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        seg_start = _coerce_float(segment.get("start"), 0.0) or 0.0
        seg_end = _coerce_float(segment.get("end"), seg_start) or seg_start
        if seg_end < seg_start:
            seg_end = seg_start
        speaker = speaker_for_interval(seg_start, seg_end)
        segment["speaker"] = speaker
        words = segment.get("words")
        if isinstance(words, list):
            for word in words:
                if isinstance(word, dict):
                    word_start = _coerce_float(word.get("start"), seg_start) or seg_start
                    word_end = _coerce_float(word.get("end"), word_start) or word_start
                    if word_end < word_start:
                        word_end = word_start
                    word["speaker"] = speaker_for_interval(word_start, word_end)
        segments_for_cleanup.append(segment)

    min_segments_per_speaker = _coerce_int(os.environ.get("WHISPERX_DIARIZATION_MIN_SEGMENTS_PER_SPEAKER"), 2) or 2
    min_segment_fraction = (
        _coerce_float(os.environ.get("WHISPERX_DIARIZATION_MIN_SEGMENT_SPEAKER_FRACTION"), 0.03) or 0.03
    )
    if min_segments_per_speaker > 1 and segments_for_cleanup:
        speaker_counts = Counter(
            _normalize_speaker(segment.get("speaker"))
            for segment in segments_for_cleanup
            if _normalize_speaker(segment.get("speaker")) != "UNKNOWN"
        )
        total_labeled_segments = sum(speaker_counts.values())
        if total_labeled_segments > 0 and len(speaker_counts) > 1:
            sparse_speakers = {
                speaker
                for speaker, count in speaker_counts.items()
                if count < min_segments_per_speaker or (float(count) / float(total_labeled_segments)) < min_segment_fraction
            }
            dominant_speakers = {speaker for speaker in speaker_counts if speaker not in sparse_speakers}
            if sparse_speakers and dominant_speakers:
                segment_centers: list[float] = []
                segment_speakers: list[str] = []
                for segment in segments_for_cleanup:
                    seg_start = _coerce_float(segment.get("start"), 0.0) or 0.0
                    seg_end = _coerce_float(segment.get("end"), seg_start) or seg_start
                    if seg_end < seg_start:
                        seg_end = seg_start
                    segment_centers.append((seg_start + seg_end) / 2.0)
                    segment_speakers.append(_normalize_speaker(segment.get("speaker")))

                for idx, segment in enumerate(segments_for_cleanup):
                    current_speaker = _normalize_speaker(segment.get("speaker"))
                    if current_speaker not in sparse_speakers:
                        continue

                    center = segment_centers[idx]
                    best_speaker = None
                    best_distance = float("inf")
                    for other_idx, other_speaker in enumerate(segment_speakers):
                        if other_idx == idx or other_speaker not in dominant_speakers:
                            continue
                        distance = abs(center - segment_centers[other_idx])
                        if distance < best_distance:
                            best_distance = distance
                            best_speaker = other_speaker
                    if best_speaker is None:
                        best_speaker = min(
                            dominant_speakers,
                            key=lambda speaker: (speaker_counts.get(speaker, 0) * -1, speaker),
                        )

                    segment["speaker"] = best_speaker
                    words = segment.get("words")
                    if isinstance(words, list):
                        for word in words:
                            if isinstance(word, dict):
                                word["speaker"] = best_speaker

    return result


def _diarize(
    *,
    audio: Any,
    audio_path: Path,
    result: dict[str, Any],
    device: str,
    token: str,
    models: list[str],
    min_speakers: int | None,
    max_speakers: int | None,
    allow_embedding_fallback: bool,
    require_pyannote: bool,
) -> tuple[dict[str, Any], str, list[str]]:
    errors: list[str] = []
    kwargs: dict[str, Any] = {}
    if min_speakers is not None:
        kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        kwargs["max_speakers"] = max_speakers

    attempts: list[tuple[str, str, str]] = []
    for model_name in models:
        if token:
            attempts.append((model_name, token, f"pyannote:{model_name}"))
        local_snapshot = _resolve_cached_model_snapshot(model_name)
        if local_snapshot is not None:
            attempts.append((str(local_snapshot), token, f"pyannote-local:{model_name}"))

    if not attempts:
        errors.append("no cached pyannote snapshot found and no token available")

    for attempt_model_name, attempt_token, backend_name in attempts:
        try:
            init_kwargs: dict[str, Any] = {
                "model_name": attempt_model_name,
                "device": device,
            }
            if attempt_token:
                init_kwargs["use_auth_token"] = attempt_token
            diarize_model = whisperx.DiarizationPipeline(**init_kwargs)
            try:
                diarize_segments = diarize_model(audio, **kwargs)
            except TypeError:
                diarize_segments = diarize_model(str(audio_path), **kwargs)
            assigned = whisperx.assign_word_speakers(diarize_segments, result)
            return assigned, backend_name, errors
        except Exception as exc:
            errors.append(f"{backend_name}: {exc}")

    if allow_embedding_fallback and not require_pyannote:
        try:
            assigned = _assign_segment_speakers_from_embeddings(
                audio=audio,
                result=result,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
            return assigned, "segment-embedding", errors
        except Exception as exc:
            errors.append(f"segment-embedding: {exc}")

    detail = " | ".join(errors) if errors else "diarization failed"
    raise RuntimeError(detail)


def run(args: argparse.Namespace) -> int:
    offline_mode = args.offline or _env_truthy("WHISPERX_OFFLINE_MODE")
    _configure_offline_mode(offline_mode)
    _configure_hf_client()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio does not exist: {input_path}")

    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    job_id = args.job_id.strip()
    if not job_id:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _sanitize(args.meeting_id.strip() or input_path.stem)
        job_id = f"{base}_{stamp}"
    job_id = _sanitize(job_id)

    job_dir = output_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = args.compute_type.strip() or "int8"
    if device == "cpu" and compute_type == "float16":
        compute_type = "int8"

    audio = whisperx.load_audio(str(input_path))
    transcript_source = "sidecar_asr"
    transcript_json_input_path = ""
    if args.transcript_json:
        transcript_json_path = Path(args.transcript_json).expanduser().resolve()
        if not transcript_json_path.exists():
            raise FileNotFoundError(f"Input transcript JSON does not exist: {transcript_json_path}")
        payload = json.loads(transcript_json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Transcript JSON root must be an object: {transcript_json_path}")
        segments = payload.get("segments")
        if not isinstance(segments, list) or not segments:
            raise RuntimeError(f"Transcript JSON has no segments: {transcript_json_path}")
        result = payload
        transcript_source = "input_json"
        transcript_json_input_path = str(transcript_json_path)
    else:
        download_root = os.environ.get("WHISPERX_DOWNLOAD_ROOT", "").strip() or os.environ.get("HF_HOME", "").strip() or None
        model = whisperx.load_model(
            args.model,
            device=device,
            compute_type=compute_type,
            language=args.language.strip() or None,
            download_root=download_root,
            local_files_only=offline_mode,
        )

        result = model.transcribe(
            audio,
            batch_size=max(args.batch_size, 1),
            language=args.language.strip() or None,
        )

    has_word_timestamps = False
    for segment in result.get("segments", []) or []:
        words = (segment or {}).get("words")
        if isinstance(words, list) and words:
            has_word_timestamps = True
            break
    if not has_word_timestamps:
        if args.language.strip() and not str(result.get("language") or "").strip():
            result["language"] = args.language.strip()
        align_model, metadata = _load_align_model(result, device)
        if align_model is not None and metadata is not None:
            result = whisperx.align(
                result.get("segments", []) or [],
                align_model,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )

    diarization_enabled = not args.no_diarization
    token = _resolve_token()
    diarization_error = ""
    diarization_backend = "none"
    diarization_attempt_errors: list[str] = []
    diarization_models = _diarization_model_list(args.diarization_models)
    embedding_fallback_default = _env_truthy("WHISPERX_DIARIZATION_EMBEDDING_FALLBACK")
    require_pyannote = args.require_pyannote or _env_truthy("WHISPERX_DIARIZATION_REQUIRE_PYANNOTE")
    allow_embedding_fallback = embedding_fallback_default and not args.no_embedding_fallback and not require_pyannote

    if diarization_enabled:
        try:
            result, diarization_backend, diarization_attempt_errors = _diarize(
                audio=audio,
                audio_path=input_path,
                result=result,
                device=device,
                token=token,
                models=diarization_models,
                min_speakers=args.min_speakers,
                max_speakers=args.max_speakers,
                allow_embedding_fallback=allow_embedding_fallback,
                require_pyannote=require_pyannote,
            )
        except Exception as exc:
            diarization_error = str(exc)
            if not args.allow_transcript_without_diarization:
                raise

    txt_path = job_dir / "transcript_diarized.txt"
    srt_path = job_dir / "transcript_diarized.srt"
    json_path = job_dir / "transcript_diarized.json"
    manifest_path = job_dir / "manifest.json"

    turn_max_gap = _coerce_float(args.turn_max_gap_seconds, 1.5) or 1.5
    turn_max_duration = _coerce_float(args.turn_max_duration_seconds, 90.0) or 90.0
    txt_lines = _build_txt_lines(
        result,
        max_gap_seconds=turn_max_gap,
        max_turn_duration_seconds=turn_max_duration,
    )
    if not txt_lines:
        for segment in result.get("segments", []) or []:
            text = str((segment or {}).get("text") or "").strip()
            if text:
                txt_lines.append(text)

    txt_path.write_text("\n".join(txt_lines).strip() + "\n", encoding="utf-8")
    srt_path.write_text("\n".join(_build_srt_lines(result)).strip() + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")

    manifest = {
        "job_id": job_id,
        "meeting_id": args.meeting_id,
        "input_audio": str(input_path),
        "output_dir": str(job_dir),
        "transcript_txt": str(txt_path),
        "transcript_srt": str(srt_path),
        "transcript_json": str(json_path),
        "created_at": _now_utc_iso(),
        "device": device,
        "model": args.model,
        "compute_type": compute_type,
        "offline_mode": offline_mode,
        "transcript_source": transcript_source,
        "transcript_json_input": transcript_json_input_path,
        "diarization_requested": diarization_enabled,
        "diarization_succeeded": diarization_enabled and not diarization_error,
        "diarization_error": diarization_error,
        "diarization_backend": diarization_backend,
        "diarization_attempt_errors": diarization_attempt_errors,
        "diarization_models": diarization_models,
        "require_pyannote": require_pyannote,
        "embedding_fallback_enabled": allow_embedding_fallback,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(manifest))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local transcription + speaker diarization in sidecar")
    parser.add_argument("--input", required=True, help="Audio file path visible from container")
    parser.add_argument(
        "--transcript-json",
        default="",
        help="Optional transcript JSON path (with segments) to diarize without running sidecar ASR",
    )
    parser.add_argument("--meeting-id", default="", help="Optional meeting ID for manifest metadata")
    parser.add_argument("--job-id", default="", help="Optional deterministic job ID")
    parser.add_argument(
        "--output-root",
        default=os.environ.get("DIARIZATION_OUTPUT_ROOT", "/shared/diarization/jobs"),
        help="Root directory for sidecar output jobs",
    )
    parser.add_argument("--model", default=os.environ.get("WHISPERX_MODEL", "large-v2"))
    parser.add_argument("--compute-type", default=os.environ.get("WHISPERX_COMPUTE_TYPE", "int8"))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("WHISPERX_BATCH_SIZE", "8")))
    parser.add_argument("--language", default=os.environ.get("WHISPERX_LANGUAGE", ""))
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run fully offline (cached models only; no Hugging Face network calls)",
    )
    parser.add_argument(
        "--diarization-models",
        default=os.environ.get(
            "WHISPERX_DIARIZATION_MODELS",
            "pyannote/speaker-diarization-3.1,pyannote/speaker-diarization",
        ),
        help="Comma-separated diarization model IDs, attempted in order",
    )
    parser.add_argument("--min-speakers", type=int, default=None)
    parser.add_argument("--max-speakers", type=int, default=None)
    parser.add_argument(
        "--turn-max-gap-seconds",
        type=float,
        default=float(os.environ.get("WHISPERX_TURN_MAX_GAP_SECONDS", "1.5")),
        help="Max silence gap within a speaker turn before splitting transcript lines",
    )
    parser.add_argument(
        "--turn-max-duration-seconds",
        type=float,
        default=float(os.environ.get("WHISPERX_TURN_MAX_DURATION_SECONDS", "90")),
        help="Split long same-speaker spans into chunks of this max duration",
    )
    parser.add_argument(
        "--no-embedding-fallback",
        action="store_true",
        help="Disable segment-embedding fallback diarization when pyannote models are unavailable",
    )
    parser.add_argument(
        "--require-pyannote",
        action="store_true",
        help="Require pyannote backend; fail diarization instead of falling back to segment embeddings",
    )
    parser.add_argument("--no-diarization", action="store_true")
    parser.add_argument(
        "--allow-transcript-without-diarization",
        action="store_true",
        help="Do not fail the job if diarization fails; emit transcript-only output with error in manifest",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:
        error = {
            "error": str(exc),
            "failed_at": _now_utc_iso(),
        }
        print(json.dumps(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
