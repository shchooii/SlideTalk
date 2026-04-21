from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from slidetalk.config import settings
from slidetalk.models import SlideInput
from slidetalk.services import generate_audio_from_script, generate_script, infer_mime_type

MAX_SECONDS_PER_SLIDE = 45
TIME_OPTIONS = [15, 30, 45]
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _format_user_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()
    if "quota exceeded" in lowered or "quota" in lowered:
        return "일일 사용 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
    return f"오류가 발생했습니다: {message}"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1280px;
        }
        h1, h2, h3 {
            letter-spacing: -0.02em;
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
            color: #5f665b;
            font-size: 0.95rem;
            line-height: 1.5;
        }
        .slidetalk-bullet {
            margin: 0.35rem 0 0;
            color: #2d3329;
            line-height: 1.5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_preview_image(uploaded, caption: str) -> None:
    try:
        st.image(uploaded, caption=caption, use_container_width=True)
    except TypeError:
        st.image(uploaded, caption=caption, use_column_width=True)


def _to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{infer_mime_type(path.name)};base64,{encoded}"


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


def _render_example_picker() -> None:
    example_images = _list_example_images()
    if not example_images:
        return

    st.markdown('<div class="slidetalk-kicker">Examples</div>', unsafe_allow_html=True)
    st.caption("예시 이미지는 Generative AI로 생성된 샘플입니다.")
    st.caption("이미지를 누르면 선택만 되고, 생성은 직접 버튼을 눌러 진행합니다.")
    columns = st.columns(min(3, len(example_images)))

    for index, image_path in enumerate(example_images):
        with columns[index % len(columns)]:
            st.markdown(
                f"""
                <a href="?example={image_path.name}" target="_self">
                    <img src="{_to_data_url(image_path)}" alt="{image_path.name}" style="width:100%; border-radius:18px; border:1px solid #e7e5db;" />
                </a>
                <div style="margin-top:0.45rem; color:#5f665b; font-size:0.9rem;">{image_path.name}</div>
                """,
                unsafe_allow_html=True,
            )


def _sidebar() -> tuple[str, str, str, int, bool, str]:
    st.sidebar.header("설정")
    audience_options = ["일반 청중", "팀원", "고객", "전문가", "교수님·심사위원", "직접 입력"]
    selected_audience = st.sidebar.selectbox("청중", audience_options, index=0)
    if selected_audience == "직접 입력":
        audience = st.sidebar.text_input("직접 입력", value="", placeholder="예: 스타트업 투자자")
    else:
        audience = selected_audience
    tone = st.sidebar.selectbox("발표 대본 스타일", ["명확하고 차분한", "자신감 있는", "친근한", "간결한"])
    st.sidebar.caption("대본의 문체와 표현 방식을 정합니다.")
    target_seconds = st.sidebar.select_slider("발표 길이", options=TIME_OPTIONS, value=30, format_func=lambda x: f"{x}초")
    extra_notes = st.sidebar.text_area("추가 요청", placeholder="예: 핵심만 짧게, 발표체로")
    st.sidebar.caption(
        f"한 장 슬라이드 전용 · Community Cloud 배포 기준 최대 {MAX_SECONDS_PER_SLIDE}초 · 현재 목표 {target_seconds}초"
    )
    enable_audio = st.sidebar.toggle("오디오 생성", value=False)
    voice_style = st.sidebar.selectbox("오디오 스타일", ["또렷한 발표", "차분한 설명", "친근한 안내"])
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


def run_app() -> None:
    st.set_page_config(page_title="SlideTalk", page_icon="🎤", layout="wide")
    _inject_styles()
    st.title("SlideTalk")
    st.caption("슬라이드 한 장으로 짧은 발표 대본을 정리합니다.")

    if not settings.is_configured:
        st.warning("`.env`에 `KANANA_API_KEY`를 설정해 주세요.")

    uploaded_file = st.file_uploader(
        "슬라이드 이미지 업로드",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=False,
        help="이미지 1장만 업로드할 수 있습니다.",
    )
    selected_example = None if uploaded_file else _get_selected_example()
    if uploaded_file:
        _clear_selected_example()

    if not uploaded_file and not selected_example:
        _render_example_picker()

    active_source = uploaded_file or selected_example
    audience, tone, extra_notes, target_seconds, enable_audio, voice_style = _sidebar()

    generate = st.button("대본 생성", disabled=not active_source or not settings.is_configured)

    script_result = None
    audio_result = None
    if generate:
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

    left, right = st.columns([1.7, 1])
    with left:
        _render_uploaded_previews(active_source)
        st.markdown('<div class="slidetalk-kicker">Script</div>', unsafe_allow_html=True)
        st.text_area(
            "script",
            value=script_result.script if script_result else "",
            height=360,
            placeholder="대본이 여기에 정리됩니다.",
            label_visibility="collapsed",
        )
    with right:
        duration_value, duration_note = _format_audio_duration(audio_result.duration_seconds if audio_result else 0)
        _render_stat_card("Duration", duration_value, duration_note)

        _render_summary_card(script_result.summary if script_result else None)
        _render_presentation_points(script_result.presentation_points if script_result else [])

        st.markdown('<div class="slidetalk-kicker">Audio</div>', unsafe_allow_html=True)
        if audio_result and audio_result.transcript:
            st.caption(audio_result.transcript)
        if audio_result and audio_result.audio_bytes:
            st.audio(audio_result.audio_bytes, format=audio_result.mime_type)
            st.download_button(
                "오디오 다운로드",
                data=audio_result.audio_bytes,
                file_name="slidetalk-script.wav",
                mime=audio_result.mime_type,
            )
        elif enable_audio and script_result:
            st.warning("이번 응답에서는 오디오 데이터를 받지 못했습니다.")
        else:
            st.write("오디오 생성 옵션을 켜면 여기에서 재생할 수 있습니다.")
