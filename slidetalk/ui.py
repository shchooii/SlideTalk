from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import streamlit as st

from slidetalk.config import settings
from slidetalk.example_cache import get_cached_targets, get_cached_voice_style, load_example_cache
from slidetalk.example_results import get_example_result
from slidetalk.models import SlideInput
from slidetalk.services import generate_audio_from_script, generate_script, infer_mime_type, normalize_audio_for_playback

MAX_SECONDS_PER_SLIDE = 45
TIME_OPTIONS = [15, 30, 45]
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
UPLOAD_RESULT_STATE_KEY = "slidetalk_uploaded_results"
TARGET_SECONDS_STATE_KEY = "slidetalk_target_seconds"


def _format_user_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()
    if "quota exceeded" in lowered or "quota" in lowered:
        return "일일 API 한도를 초과했습니다. 내일 다시 시도해 주세요."
    return f"오류가 발생했습니다: {message}"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --slidetalk-bg: #f7f7f2;
            --slidetalk-panel: #ffffff;
            --slidetalk-border: #e7e5db;
            --slidetalk-text: #1f241c;
            --slidetalk-muted: #5f665b;
            --slidetalk-accent: #2f7dc4;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(96, 165, 250, 0.12), transparent 26%),
                radial-gradient(circle at top right, rgba(110, 231, 183, 0.10), transparent 20%),
                linear-gradient(180deg, #fbfbf8 0%, #f3f4ee 100%);
        }
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1280px;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(244, 247, 241, 0.98) 100%);
            border-right: 1px solid var(--slidetalk-border);
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 1rem;
        }
        h1, h2, h3 {
            letter-spacing: -0.02em;
        }
        [data-testid="stFileUploader"] section {
            border-radius: 18px;
        }
        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseButton-primary"] {
            border-radius: 999px;
        }
        .stTextArea textarea {
            font-size: 1rem;
            line-height: 1.7;
            border-radius: 18px;
        }
        .slidetalk-card {
            background: linear-gradient(180deg, #ffffff 0%, #f6f7f3 100%);
            border: 1px solid #e7e5db;
            border-radius: 22px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.9rem;
            box-shadow: 0 10px 30px rgba(28, 31, 24, 0.05);
        }
        .slidetalk-kicker {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: #7a7f73;
            margin-bottom: 0.35rem;
        }
        .slidetalk-value {
            font-size: 1.8rem;
            font-weight: 700;
            line-height: 1.1;
            color: #1f241c;
        }
        .slidetalk-note {
            color: var(--slidetalk-muted);
            font-size: 0.95rem;
            line-height: 1.5;
        }
        .slidetalk-bullet {
            margin: 0.35rem 0 0;
            color: #2d3329;
            line-height: 1.5;
        }
        .slidetalk-hero {
            padding: 1rem 1.15rem;
            border-radius: 22px;
            margin-bottom: 0.9rem;
            background: linear-gradient(135deg, rgba(47, 125, 196, 0.92) 0%, rgba(29, 78, 216, 0.80) 48%, rgba(15, 118, 110, 0.78) 100%);
            color: #f8fbff;
            box-shadow: 0 12px 32px rgba(28, 31, 24, 0.10);
        }
        .slidetalk-hero-title {
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1.1;
            margin: 0;
        }
        .slidetalk-hero-link {
            display: inline-flex;
            align-items: center;
            margin-top: 0.45rem;
            padding: 0.45rem 0.75rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.18);
            color: #ffffff !important;
            font-size: 0.92rem;
            font-weight: 600;
            text-decoration: none !important;
        }
        .slidetalk-hero-meta {
            margin-top: 0.45rem;
            color: rgba(248, 251, 255, 0.86);
            font-size: 0.92rem;
            line-height: 1.5;
        }
        .slidetalk-hero-note {
            margin-top: 0.85rem;
            max-width: 680px;
            color: rgba(248, 251, 255, 0.86);
            font-size: 0.96rem;
            line-height: 1.5;
        }
        .slidetalk-banner {
            border-radius: 18px;
            padding: 0.95rem 1rem;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, rgba(255,255,255,0.92) 0%, rgba(244, 247, 241, 0.92) 100%);
            border: 1px solid var(--slidetalk-border);
        }
        .slidetalk-banner strong {
            color: var(--slidetalk-text);
        }
        .slidetalk-empty {
            border-radius: 22px;
            padding: 1.1rem 1.15rem;
            margin-bottom: 1rem;
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid var(--slidetalk-border);
            box-shadow: 0 10px 30px rgba(28, 31, 24, 0.05);
        }
        .slidetalk-empty-title {
            color: var(--slidetalk-text);
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .slidetalk-inline-actions {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.5rem;
            flex-wrap: wrap;
        }
        .slidetalk-preview [data-testid="stImage"] img {
            max-width: 78%;
            margin: 0 auto;
            display: block;
        }
        .slidetalk-preview [data-testid="stImageCaption"] {
            text-align: center;
        }
        @media (max-width: 900px) {
            .block-container {
                padding-top: 1rem;
                padding-left: 0.9rem;
                padding-right: 0.9rem;
            }
            .slidetalk-hero {
                padding: 1.1rem 1rem;
                border-radius: 20px;
            }
            .slidetalk-hero-title {
                font-size: 1.7rem;
            }
            .slidetalk-desktop-only {
                display: none;
            }
            [data-testid="stHorizontalBlock"] {
                gap: 0.75rem;
            }
            [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
            }
            .slidetalk-preview [data-testid="stImage"] img {
                max-width: 100%;
            }
        }
        @media (min-width: 901px) {
            .slidetalk-mobile-only {
                display: none;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_preview_image(uploaded, caption: str) -> None:
    st.markdown('<div class="slidetalk-preview">', unsafe_allow_html=True)
    try:
        st.image(uploaded, caption=caption, use_container_width=True)
    except TypeError:
        st.image(uploaded, caption=caption, use_column_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{infer_mime_type(path.name)};base64,{encoded}"


def _audio_to_data_url(audio_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _list_example_images() -> list[Path]:
    if not EXAMPLES_DIR.exists():
        return []
    files = [path for path in sorted(EXAMPLES_DIR.iterdir()) if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    return files


def _load_slide(source) -> list[SlideInput]:
    if not source:
        return []

    if isinstance(source, Path):
        return [
            SlideInput(
                filename=source.name,
                mime_type=infer_mime_type(source.name),
                data=source.read_bytes(),
            )
        ]

    return [
        SlideInput(
            filename=source.name,
            mime_type=source.type or infer_mime_type(source.name),
            data=source.getvalue(),
        )
    ]


def _render_uploaded_previews(source) -> None:
    if not source:
        st.markdown(
            '<div class="slidetalk-card"><div class="slidetalk-note">업로드한 슬라이드가 여기에 표시됩니다.</div></div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="slidetalk-kicker">Slides</div>', unsafe_allow_html=True)
    if isinstance(source, Path):
        _render_preview_image(str(source), caption=source.name)
    else:
        _render_preview_image(source, caption=source.name)


def _get_selected_example() -> Path | None:
    example_images = _list_example_images()
    selected_name = st.query_params.get("example")
    if not example_images or not selected_name:
        return None

    for image_path in example_images:
        if image_path.name == selected_name:
            return image_path
    return None


def _clear_selected_example() -> None:
    if "example" in st.query_params:
        del st.query_params["example"]


def _render_example_picker(selected_name: str | None) -> None:
    example_images = _list_example_images()
    if not example_images:
        return

    st.markdown('<div class="slidetalk-kicker">Examples</div>', unsafe_allow_html=True)
    st.caption("예시는 드롭다운에서 고를 수 있습니다.")
    names = [image_path.name for image_path in example_images]
    options = ["선택 안 함", *names]
    current_value = selected_name if selected_name in names else "선택 안 함"
    picked = st.selectbox(
        "예시 선택",
        options,
        index=options.index(current_value),
        key="example-picker",
        label_visibility="collapsed",
    )

    if picked == "선택 안 함":
        if selected_name:
            _clear_selected_example()
            st.rerun()
        return

    if picked != selected_name:
        st.query_params["example"] = picked
        st.rerun()


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="slidetalk-empty slidetalk-mobile-only">
            <div class="slidetalk-empty-title">시작하기</div>
            <div class="slidetalk-note">데스크톱에서는 왼쪽 사이드바에서 발표 길이와 스타일을 먼저 설정할 수 있습니다.</div>
            <div class="slidetalk-note">이미지를 업로드하면 결과를 새로 생성해줍니다. 일일 10회 API 한도가 있습니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_controls() -> tuple[str, str, str, int, bool, str]:
    audience_options = ["일반 청중", "팀원", "고객", "전문가", "교수님·심사위원", "직접 입력"]
    st.sidebar.header("설정")
    selected_audience = st.sidebar.selectbox("청중", audience_options, index=0)
    tone = st.sidebar.selectbox("발표 대본 스타일", ["명확하고 차분한", "자신감 있는", "친근한", "간결한"])

    audience = selected_audience
    if selected_audience == "직접 입력":
        audience = st.sidebar.text_input("직접 입력", value="", placeholder="예: 스타트업 투자자")

    if TARGET_SECONDS_STATE_KEY not in st.session_state:
        st.session_state[TARGET_SECONDS_STATE_KEY] = 30
    target_seconds = st.sidebar.select_slider(
        "발표 길이",
        options=TIME_OPTIONS,
        value=st.session_state[TARGET_SECONDS_STATE_KEY],
        key=TARGET_SECONDS_STATE_KEY,
        format_func=lambda x: f"{x}초",
    )
    extra_notes = st.sidebar.text_area("추가 요청", placeholder="예: 핵심만 짧게, 발표체로")
    st.sidebar.caption(f"한 장 슬라이드 전용 · 최대 {MAX_SECONDS_PER_SLIDE}초 · 현재 목표 {target_seconds}초")
    enable_audio = st.sidebar.toggle("오디오 생성", value=True)
    voice_style = st.sidebar.selectbox("오디오 스타일", ["또렷한 발표", "차분한 설명", "친근한 안내"], disabled=not enable_audio)
    return (audience, tone, extra_notes, target_seconds, enable_audio, voice_style)


def _format_duration(estimated_minutes: float, slide_count: int) -> tuple[str, str]:
    total_seconds = max(0, int(round(estimated_minutes * 60)))
    total_seconds = min(total_seconds, MAX_SECONDS_PER_SLIDE)
    if slide_count <= 1 or total_seconds < 60:
        return f"{total_seconds}초", f"한 장 발표 기준 · 최대 {MAX_SECONDS_PER_SLIDE}초"

    minutes, seconds = divmod(total_seconds, 60)
    if seconds == 0:
        return f"{minutes}분", "전체 발표 기준"
    return f"{minutes}분 {seconds}초", "전체 발표 기준"


def _format_audio_duration(duration_seconds: int) -> tuple[str, str]:
    if duration_seconds <= 0:
        return "-", "오디오 생성 후 실제 재생 시간으로 표시됩니다."
    if duration_seconds < 60:
        return f"{duration_seconds}초", "실제 오디오 길이"
    minutes, seconds = divmod(duration_seconds, 60)
    if seconds == 0:
        return f"{minutes}분", "실제 오디오 길이"
    return f"{minutes}분 {seconds}초", "실제 오디오 길이"


def _render_stat_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="slidetalk-card">
            <div class="slidetalk-kicker">{label}</div>
            <div class="slidetalk-value">{value}</div>
            <div class="slidetalk-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_card(summary: str | None) -> None:
    text = summary or "생성된 요약이 아직 없습니다."
    st.markdown(
        f"""
        <div class="slidetalk-card">
            <div class="slidetalk-kicker">Summary</div>
            <div class="slidetalk-note">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_presentation_points(points: list[str]) -> None:
    if points:
        items = "".join([f'<div class="slidetalk-bullet">• {point}</div>' for point in points])
    else:
        items = '<div class="slidetalk-note">발표 포인트가 아직 없습니다.</div>'
    st.markdown(
        f"""
        <div class="slidetalk-card">
            <div class="slidetalk-kicker">Presentation Points</div>
            {items}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _source_id(source) -> str:
    if isinstance(source, Path):
        return f"example:{source.name}"
    digest = hashlib.sha1(source.getvalue()).hexdigest()[:12]
    return f"upload:{source.name}:{digest}"


def _get_uploaded_results_state() -> dict:
    return st.session_state.setdefault(UPLOAD_RESULT_STATE_KEY, {})


def _get_cached_uploaded_results(source_id: str) -> dict:
    return _get_uploaded_results_state().get(source_id, {})


def _store_uploaded_result(source_id: str, target_seconds: int, script_result, audio_result) -> None:
    cached = _get_uploaded_results_state().setdefault(source_id, {})
    cached[target_seconds] = {
        "script_result": script_result,
        "audio_result": audio_result,
    }


def _render_source_banner(source, is_example: bool, target_seconds: int) -> None:
    if not source:
        return

    if is_example:
        message = f"<strong>{source.name}</strong> · 미리 돌려둔 예시 결과 · {target_seconds}초"
    else:
        message = f"<strong>{source.name}</strong> · 새 이미지 API 호출 가능 · 일일 한도 있음"

    st.markdown(f'<div class="slidetalk-banner">{message}</div>', unsafe_allow_html=True)


def _render_example_cache_status(filename: str) -> None:
    cached_targets = get_cached_targets(filename)
    if not cached_targets:
        return

    label = ", ".join([f"{seconds}초" for seconds in sorted(cached_targets)])
    voice_style = get_cached_voice_style(filename)
    if voice_style:
        st.caption(f"미리 돌려놓은 생성된 결과입니다. · 오디오 스타일: {voice_style}")
    else:
        st.caption("미리 돌려놓은 생성된 결과입니다.")


def _get_example_variant(filename: str, target_seconds: int):
    script_result, audio_result = load_example_cache(filename, target_seconds)
    if not script_result:
        script_result = get_example_result(filename, target_seconds)
    return script_result, audio_result


def _render_audio_panel(script_result, audio_result, is_example: bool, key_suffix: str) -> None:
    st.markdown('<div class="slidetalk-kicker">Audio</div>', unsafe_allow_html=True)
    if audio_result and audio_result.transcript:
        st.caption(audio_result.transcript)
    if audio_result and audio_result.audio_bytes:
        playback_audio, playback_mime = normalize_audio_for_playback(audio_result.audio_bytes, audio_result.mime_type)
        audio_src = _audio_to_data_url(playback_audio, playback_mime)
        st.markdown(
            f"""
            <audio controls preload="metadata" playsinline style="width: 100%;">
                <source src="{audio_src}" type="{playback_mime}">
                브라우저가 오디오 재생을 지원하지 않습니다.
            </audio>
            """,
            unsafe_allow_html=True,
        )
        st.download_button(
            "오디오 다운로드",
            data=playback_audio,
            file_name=f"slidetalk-script-{key_suffix}.wav",
            mime=playback_mime,
            key=f"download-audio-{key_suffix}",
        )
    elif is_example and script_result:
        st.info("이 예시에는 저장된 오디오가 없습니다.")
    elif script_result:
        st.warning("이번 응답에서는 오디오 데이터를 받지 못했습니다.")
    else:
        st.write("오디오 생성 옵션을 켜면 여기에서 재생할 수 있습니다.")


def run_app() -> None:
    st.set_page_config(page_title="SlideTalk", page_icon="🎤", layout="wide", initial_sidebar_state="expanded")
    _inject_styles()
    st.markdown(
        """
        <div class="slidetalk-hero">
            <div class="slidetalk-hero-title">SlideTalk</div>
            <a class="slidetalk-hero-link" href="https://api-omni.kanana.ai/result" target="_blank" rel="noopener noreferrer">kanana-o model</a>
            <div class="slidetalk-hero-meta">kanana-o 멀티모달 언어모델을 사용해 대본 텍스트와 오디오를 생성합니다. </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "슬라이드 이미지 업로드",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=False,
        help="이미지 1장만 업로드할 수 있습니다.",
    )
    selected_example = None if uploaded_file else _get_selected_example()
    if uploaded_file:
        _clear_selected_example()

    if not settings.is_configured and not selected_example:
        st.warning("새 이미지 호출에는 `KANANA_API_KEY`가 필요합니다.")
    elif not settings.is_configured:
        st.info("예시는 바로 볼 수 있고, 새 이미지는 API 키가 있어야 호출할 수 있습니다.")

    audience, tone, extra_notes, target_seconds, enable_audio, voice_style = _render_controls()

    if not uploaded_file and not selected_example:
        _render_empty_state()
        _render_example_picker(st.query_params.get("example"))

    active_source = uploaded_file or selected_example
    is_example = isinstance(active_source, Path)
    _render_source_banner(active_source, is_example=is_example, target_seconds=target_seconds)

    if selected_example and not uploaded_file:
        st.markdown('<div class="slidetalk-inline-actions">', unsafe_allow_html=True)
        st.caption(f"선택한 예시: {selected_example.name}")
        if st.button("예시 선택 해제", use_container_width=False):
            _clear_selected_example()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    can_generate_upload = bool(uploaded_file and settings.is_configured)
    generate = False
    if uploaded_file:
        generate = st.button("대본 생성", disabled=not settings.is_configured)

    script_result = None
    audio_result = None
    source_id = _source_id(active_source) if active_source else ""

    if is_example and active_source:
        script_result, audio_result = _get_example_variant(active_source.name, target_seconds)
    elif source_id:
        cached_result = _get_cached_uploaded_results(source_id).get(target_seconds)
        if cached_result:
            script_result = cached_result["script_result"]
            audio_result = cached_result["audio_result"]

    if generate and uploaded_file and can_generate_upload:
        slides = _load_slide(active_source)
        try:
            with st.spinner("슬라이드를 읽고 발표 대본을 만드는 중입니다..."):
                script_result = generate_script(
                    slides=slides,
                    audience=audience,
                    tone=tone,
                    extra_notes=extra_notes,
                    target_seconds=target_seconds,
                )
        except Exception as exc:
            st.error(_format_user_error(exc))
            return

        if enable_audio and script_result.script.strip():
            try:
                with st.spinner("오디오를 생성하는 중입니다..."):
                    audio_result = generate_audio_from_script(script_result.script, voice_style)
            except Exception as exc:
                st.error(_format_user_error(exc))
                return

        _store_uploaded_result(source_id, target_seconds, script_result, audio_result)

    if is_example and active_source:
        _render_example_cache_status(active_source.name)
        left, right = st.columns([1, 1.1])
        with left:
            _render_uploaded_previews(active_source)
            st.markdown('<div class="slidetalk-kicker">Script</div>', unsafe_allow_html=True)
            st.text_area(
                f"script-example-selected-{active_source.stem}-{target_seconds}",
                value=script_result.script if script_result else "",
                height=320,
                placeholder="대본이 여기에 정리됩니다.",
                label_visibility="collapsed",
            )
        with right:
            if audio_result and audio_result.duration_seconds:
                duration_value, duration_note = _format_audio_duration(audio_result.duration_seconds)
            elif script_result:
                duration_value, duration_note = _format_duration(script_result.estimated_minutes, 1)
            else:
                duration_value, duration_note = "-", "대본 생성 후 예상 시간을 표시합니다."
            _render_stat_card("Duration", duration_value, duration_note)
            _render_summary_card(script_result.summary if script_result else None)
            _render_presentation_points(script_result.presentation_points if script_result else [])
            _render_audio_panel(script_result, audio_result, True, f"example-{active_source.stem}-{target_seconds}")
    else:
        left, right = st.columns([1, 1.1])
        with left:
            _render_uploaded_previews(active_source)
            st.markdown('<div class="slidetalk-kicker">Script</div>', unsafe_allow_html=True)
            st.text_area(
                f"script-{source_id or 'empty'}-{target_seconds}",
                value=script_result.script if script_result else "",
                height=360,
                placeholder="대본이 여기에 정리됩니다.",
                label_visibility="collapsed",
            )
        with right:
            if audio_result and audio_result.duration_seconds:
                duration_value, duration_note = _format_audio_duration(audio_result.duration_seconds)
            elif script_result:
                duration_value, duration_note = _format_duration(script_result.estimated_minutes, 1)
            else:
                duration_value, duration_note = "-", "대본 생성 후 예상 시간을 표시합니다."
            _render_stat_card("Duration", duration_value, duration_note)

            _render_summary_card(script_result.summary if script_result else None)
            _render_presentation_points(script_result.presentation_points if script_result else [])
            _render_audio_panel(script_result, audio_result, False, "upload")
