SCRIPT_SYSTEM_PROMPT = """
You are a presentation coach.
Create a clear Korean speaking script based on slide images.
Keep the output practical for a real presenter.

Return valid JSON with this exact shape:
{
  "summary": "one short summary",
  "presentation_points": ["point 1", "point 2", "point 3"],
  "script": "full Korean presentation script",
  "estimated_minutes": 3.5
}

Rules:
- Assume the uploaded images are presentation slides in order.
- Write natural spoken Korean.
- Keep the structure easy to rehearse.
- Estimate presentation time based on normal speaking speed.
- Do not wrap the JSON in markdown fences.
""".strip()


def build_script_user_prompt(audience: str, tone: str, extra_notes: str) -> str:
    notes = extra_notes.strip() or "없음"
    return f"""
슬라이드 이미지를 순서대로 보고 발표 대본을 작성해 주세요.

발표 청중: {audience}
발표 톤: {tone}
추가 요청사항: {notes}
""".strip()


def build_script_constraints(
    slide_count: int,
    target_seconds_per_slide: int,
    max_seconds_per_slide: int,
) -> str:
    target_total_seconds = slide_count * target_seconds_per_slide
    max_total_seconds = slide_count * max_seconds_per_slide
    return f"""
시간 제약을 반드시 지켜 주세요.

슬라이드 수: {slide_count}장
목표 시간: 슬라이드당 약 {target_seconds_per_slide}초, 총 {target_total_seconds}초 이내 권장
최대 시간: 슬라이드당 {max_seconds_per_slide}초 이하, 총 {max_total_seconds}초를 넘기지 말 것
구성: 군더더기 없이 바로 발표 가능한 말투로 작성하고, "요약부터 드릴게요" 같은 메타 문장은 넣지 말 것
 presentation_points 규칙: 발표자가 짚어 말할 짧은 핵심 항목으로 작성할 것

결과는 간결한 요약, 발표 포인트, 전체 발표 대본, 예상 발표 시간(분)으로 정리해 주세요.
""".strip()


def build_audio_instruction(script: str, voice_style: str) -> str:
    return f"""
다음 발표 대본을 한국어 음성으로 읽어 주세요.
말투는 {voice_style} 느낌으로 자연스럽게 유지해 주세요.

대본:
{script}
""".strip()
