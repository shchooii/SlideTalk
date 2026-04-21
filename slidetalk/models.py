from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SlideInput:
    filename: str
    mime_type: str
    data: bytes


@dataclass
class ScriptResult:
    script: str
    estimated_minutes: float
    summary: str = ""
    presentation_points: list[str] = field(default_factory=list)


@dataclass
class AudioResult:
    transcript: str
    audio_bytes: bytes | None = None
    mime_type: str = "audio/wav"
    duration_seconds: int = 0
