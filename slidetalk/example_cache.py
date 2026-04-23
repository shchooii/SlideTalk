from __future__ import annotations

import json
from pathlib import Path

from slidetalk.models import AudioResult, ScriptResult

CACHE_DIR = Path(__file__).resolve().parent.parent / "example_cache"


def _example_dir(filename: str) -> Path:
    return CACHE_DIR / Path(filename).stem


def _manifest_path(filename: str) -> Path:
    return _example_dir(filename) / "manifest.json"


def _audio_path(filename: str, target_seconds: int) -> Path:
    return _example_dir(filename) / f"{target_seconds}.wav"


def load_example_cache(filename: str, target_seconds: int) -> tuple[ScriptResult | None, AudioResult | None]:
    manifest_path = _manifest_path(filename)
    if not manifest_path.exists():
        return None, None

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None

    result_payload = (payload.get("results") or {}).get(str(target_seconds))
    if not isinstance(result_payload, dict):
        return None, None

    script_result = ScriptResult(
        script=str(result_payload.get("script") or ""),
        estimated_minutes=float(result_payload.get("estimated_minutes") or 0),
        summary=str(result_payload.get("summary") or ""),
        presentation_points=[str(point) for point in (result_payload.get("presentation_points") or [])],
    )

    audio_file = _audio_path(filename, target_seconds)
    audio_bytes = audio_file.read_bytes() if audio_file.exists() else None
    audio_result = AudioResult(
        transcript=str(result_payload.get("transcript") or ""),
        audio_bytes=audio_bytes,
        mime_type=str(result_payload.get("mime_type") or "audio/wav"),
        duration_seconds=int(result_payload.get("duration_seconds") or 0),
    )
    return script_result, audio_result


def get_cached_targets(filename: str) -> set[int]:
    manifest_path = _manifest_path(filename)
    if not manifest_path.exists():
        return set()

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    results = payload.get("results") or {}
    return {int(key) for key in results.keys() if str(key).isdigit()}


def save_example_cache(
    filename: str,
    target_seconds: int,
    script_result: ScriptResult,
    audio_result: AudioResult | None,
    voice_style: str,
) -> None:
    example_dir = _example_dir(filename)
    example_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _manifest_path(filename)

    payload: dict[str, object] = {"results": {}, "voice_style": voice_style}
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"results": {}, "voice_style": voice_style}

    results = payload.setdefault("results", {})
    if not isinstance(results, dict):
        results = {}
        payload["results"] = results

    results[str(target_seconds)] = {
        "script": script_result.script,
        "estimated_minutes": script_result.estimated_minutes,
        "summary": script_result.summary,
        "presentation_points": script_result.presentation_points,
        "transcript": audio_result.transcript if audio_result else "",
        "mime_type": audio_result.mime_type if audio_result else "audio/wav",
        "duration_seconds": audio_result.duration_seconds if audio_result else 0,
    }
    payload["voice_style"] = voice_style

    if audio_result and audio_result.audio_bytes:
        _audio_path(filename, target_seconds).write_bytes(audio_result.audio_bytes)

    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_cached_voice_style(filename: str) -> str:
    manifest_path = _manifest_path(filename)
    if not manifest_path.exists():
        return ""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("voice_style") or "")
