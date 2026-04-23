from __future__ import annotations

import base64
import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
import wave
from array import array
from io import BytesIO

from openai import OpenAI
from PIL import Image

from slidetalk.config import settings
from slidetalk.models import AudioResult, ScriptResult, SlideInput
from slidetalk.prompts import (
    SCRIPT_SYSTEM_PROMPT,
    build_audio_instruction,
    build_script_constraints,
    build_script_user_prompt,
)

INPUT_SAMPLE_RATE = 24000
PLAYBACK_SAMPLE_RATE = 44100
SAMPLE_WIDTH = 2
CHANNELS = 1
MAX_IMAGE_SIDE = 1280
JPEG_QUALITY = 85
MAX_SECONDS_PER_SLIDE = 45
DEFAULT_TARGET_SECONDS = 30
META_PHRASES = [
    "요약부터 드릴게요",
    "요약부터 말씀드리면",
    "정리해서 말씀드리면",
    "간단히 말씀드리면",
    "먼저 요약하면",
]


def get_client() -> OpenAI:
    return OpenAI(base_url=settings.base_url, api_key=settings.api_key)


def _as_data_url(slide: SlideInput) -> str:
    encoded = base64.b64encode(slide.data).decode("utf-8")
    return f"data:{slide.mime_type};base64,{encoded}"


def _optimize_slide(slide: SlideInput) -> SlideInput:
    try:
        with Image.open(BytesIO(slide.data)) as img:
            img = img.convert("RGB")
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return SlideInput(
                filename=slide.filename,
                mime_type="image/jpeg",
                data=buffer.getvalue(),
            )
    except Exception:
        return slide


def _estimate_minutes_from_script(script: str) -> float:
    text = re.sub(r"\s+", " ", script).strip()
    if not text:
        return 0.0
    estimated_seconds = len(text) / 8.5
    return round(estimated_seconds / 60.0, 1)


def _target_max_tokens(target_seconds: int) -> int:
    return max(100, min(320, int(target_seconds * 4.5)))


def _trim_script(script: str, max_characters: int) -> str:
    text = re.sub(r"\s+", " ", script).strip()
    if len(text) <= max_characters:
        return text

    truncated = text[:max_characters].rstrip()
    last_break = max(truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? "), truncated.rfind("."))
    if last_break >= max_characters // 2:
        truncated = truncated[: last_break + 1].rstrip()
    return truncated


def _strip_meta_phrases(text: str) -> str:
    cleaned = text.strip()
    for phrase in META_PHRASES:
        cleaned = re.sub(rf"^{re.escape(phrase)}[\s,.:;!-]*", "", cleaned)
    return cleaned.strip()


def _extract_json_payload(raw_content: str) -> dict:
    text = raw_content.strip()
    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def _fallback_summary(script_text: str) -> str:
    sentences = _split_sentences(script_text)
    if not sentences:
        return ""
    summary = " ".join(sentences[:2]).strip()
    return _strip_meta_phrases(summary[:140].rstrip())


def _normalize_key_point(text: str) -> str:
    point = _strip_meta_phrases(re.sub(r"\s+", " ", text).strip(" .,-"))
    point = re.sub(r"^(먼저|그리고|또한|마지막으로|즉|결국)\s+", "", point)
    return point[:36].rstrip()


def _fallback_key_points(script_text: str) -> list[str]:
    candidates: list[str] = []
    for sentence in _split_sentences(script_text):
        chunks = re.split(r",| 그리고 | 또한 | 특히 | 먼저 | 다음으로 | 마지막으로 | 즉 ", sentence)
        for chunk in chunks:
            point = _normalize_key_point(chunk)
            if not point:
                continue
            if len(point) < 6:
                continue
            if len(point.split()) > 8:
                continue
            if point not in candidates:
                candidates.append(point)
            if len(candidates) == 3:
                return candidates
    return candidates[:3]


def _request_json_response(
    client: OpenAI,
    messages: list[dict],
    max_tokens: int,
):
    return client.chat.completions.create(
        model=settings.model,
        response_format={"type": "json_object"},
        messages=messages,
        max_tokens=max_tokens,
    )


def generate_script(
    slides: list[SlideInput],
    audience: str,
    tone: str,
    extra_notes: str,
    target_seconds: int = DEFAULT_TARGET_SECONDS,
) -> ScriptResult:
    client = get_client()
    optimized_slides = [_optimize_slide(slide) for slide in slides]
    target_seconds = max(15, min(target_seconds, MAX_SECONDS_PER_SLIDE))
    max_tokens = _target_max_tokens(target_seconds)
    max_characters = int(target_seconds * 7)
    prompt_text = "\n\n".join(
        [
            build_script_user_prompt(audience, tone, extra_notes),
            build_script_constraints(
                slide_count=len(optimized_slides),
                target_seconds_per_slide=target_seconds,
                max_seconds_per_slide=MAX_SECONDS_PER_SLIDE,
            ),
        ]
    )
    content: list[dict] = [{"type": "text", "text": prompt_text}]
    for slide in optimized_slides:
        content.append({"type": "image_url", "image_url": {"url": _as_data_url(slide)}})

    response = _request_json_response(
        client=client,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )

    raw_content = response.choices[0].message.content or ""
    payload = _extract_json_payload(raw_content)
    script_text = (payload.get("script") or "").strip()
    if not script_text:
        script_text = raw_content.strip()
    script_text = _strip_meta_phrases(script_text)
    script_text = _trim_script(script_text, max_characters)

    estimated_minutes = payload.get("estimated_minutes")
    if estimated_minutes in (None, ""):
        estimated_minutes = _estimate_minutes_from_script(script_text)

    max_total_minutes = round((len(optimized_slides) * MAX_SECONDS_PER_SLIDE) / 60, 1)
    if estimated_minutes:
        estimated_minutes = min(float(estimated_minutes), max_total_minutes)

    summary = _strip_meta_phrases((payload.get("summary") or "").strip())
    raw_presentation_points = payload.get("presentation_points") or payload.get("key_points") or []
    presentation_points = []
    for point in raw_presentation_points:
        normalized = _normalize_key_point(str(point))
        if normalized and normalized not in presentation_points:
            presentation_points.append(normalized)
    summary = summary or _fallback_summary(script_text)
    presentation_points = presentation_points or _fallback_key_points(script_text)

    return ScriptResult(
        summary=summary,
        presentation_points=presentation_points,
        script=script_text,
        estimated_minutes=float(estimated_minutes or 0),
    )


def _pcm_chunks_to_wav(pcm_chunks: list[bytes]) -> bytes | None:
    if not pcm_chunks:
        return None

    pcm_data = b"".join(pcm_chunks)
    pcm_data = _resample_pcm16_mono(pcm_data, INPUT_SAMPLE_RATE, PLAYBACK_SAMPLE_RATE)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(PLAYBACK_SAMPLE_RATE)
        wf.writeframes(pcm_data)
    return buffer.getvalue()


def _resample_pcm16_mono(pcm_data: bytes, input_rate: int, output_rate: int) -> bytes:
    if not pcm_data or input_rate == output_rate:
        return pcm_data

    try:
        import audioop

        converted, _ = audioop.ratecv(pcm_data, SAMPLE_WIDTH, CHANNELS, input_rate, output_rate, None)
        return converted
    except Exception:
        pass

    samples = array("h")
    samples.frombytes(pcm_data)
    if not samples:
        return pcm_data

    output_length = max(1, int(round(len(samples) * output_rate / input_rate)))
    step = input_rate / output_rate
    resampled = array("h")
    for index in range(output_length):
        position = index * step
        left = int(position)
        right = min(left + 1, len(samples) - 1)
        fraction = position - left
        sample = int(round(samples[left] * (1 - fraction) + samples[right] * fraction))
        resampled.append(sample)
    return resampled.tobytes()


def normalize_audio_for_playback(audio_bytes: bytes | None, mime_type: str) -> tuple[bytes | None, str]:
    if not audio_bytes:
        return None, mime_type

    if mime_type not in {"audio/wav", "audio/wave", "audio/x-wav"}:
        return audio_bytes, mime_type

    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
            if wav_file.getnchannels() != CHANNELS or wav_file.getsampwidth() != SAMPLE_WIDTH:
                return audio_bytes, "audio/wav"
            frames = wav_file.readframes(wav_file.getnframes())
            converted = _resample_pcm16_mono(frames, wav_file.getframerate(), PLAYBACK_SAMPLE_RATE)
    except Exception:
        return audio_bytes, "audio/wav"

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(PLAYBACK_SAMPLE_RATE)
        wav_file.writeframes(converted)
    return buffer.getvalue(), "audio/wav"


def _audio_format_to_mime(audio_format: str) -> str:
    mapping = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "pcm16": "audio/wav",
        "flac": "audio/flac",
        "opus": "audio/ogg",
    }
    return mapping.get(audio_format, "audio/wav")


def _audio_format_to_extension(audio_format: str) -> str:
    mapping = {
        "mp3": "mp3",
        "mpeg": "mp3",
        "wav": "wav",
        "pcm16": "wav",
        "flac": "flac",
        "opus": "ogg",
        "ogg": "ogg",
    }
    return mapping.get(audio_format, "wav")


def _maybe_convert_wav_to_mp3(audio_bytes: bytes | None, mime_type: str) -> tuple[bytes | None, str]:
    if not audio_bytes or mime_type not in {"audio/wav", "audio/wave", "audio/x-wav"}:
        return audio_bytes, mime_type

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return audio_bytes, mime_type

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = f"{temp_dir}/input.wav"
        output_path = f"{temp_dir}/output.mp3"
        with open(input_path, "wb") as input_file:
            input_file.write(audio_bytes)

        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                input_path,
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                output_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return audio_bytes, mime_type

        try:
            with open(output_path, "rb") as output_file:
                return output_file.read(), "audio/mpeg"
        except Exception:
            return audio_bytes, mime_type


def _collect_streamed_audio(response, requested_format: str = "wav") -> AudioResult:
    transcript = ""
    audio_chunks: list[bytes] = []

    for chunk in response:
        raw = chunk.model_dump()
        choices = raw.get("choices") or []
        if not choices:
            continue

        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str) and content:
            cleaned = content.strip()
            if cleaned:
                if cleaned.startswith(transcript):
                    transcript = cleaned
                elif transcript and transcript.endswith(cleaned):
                    pass
                else:
                    transcript += content

        audio = delta.get("audio")
        audio_b64_data = None
        if isinstance(audio, str):
            audio_b64_data = audio
        elif isinstance(audio, dict):
            audio_b64_data = audio.get("data") or audio.get("audio")

        if isinstance(audio_b64_data, str) and audio_b64_data:
            audio_chunks.append(base64.b64decode(audio_b64_data, validate=True))

    duration_seconds = 0
    mime_type = _audio_format_to_mime(requested_format)
    audio_bytes: bytes | None
    if requested_format in {"wav", "pcm16"}:
        total_pcm_bytes = sum(len(chunk) for chunk in audio_chunks)
        if total_pcm_bytes:
            bytes_per_second = INPUT_SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS
            duration_seconds = int(round(total_pcm_bytes / bytes_per_second))
        audio_bytes = _pcm_chunks_to_wav(audio_chunks)
        mime_type = "audio/wav"
    else:
        audio_bytes = b"".join(audio_chunks) if audio_chunks else None

    if audio_bytes and requested_format in {"wav", "pcm16"}:
        audio_bytes, mime_type = _maybe_convert_wav_to_mp3(audio_bytes, mime_type)

    return AudioResult(
        transcript=transcript.strip(),
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
    )


def _request_audio_response(client: OpenAI, script: str, voice_style: str):
    return client.chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": build_audio_instruction(script, voice_style)}],
            }
        ],
        modalities=["text", "audio"],
        stream=True,
    )


def generate_audio_from_script(script: str, voice_style: str) -> AudioResult:
    client = get_client()
    response = _request_audio_response(client, script, voice_style)
    return _collect_streamed_audio(response, "wav")


def infer_mime_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "image/png"
