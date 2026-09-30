"""세션 요약 프롬프트 빌더 단위 테스트.

``ai_worker/domains/rag/prompt_builder.py`` 의 system/user prompt 빌더와
``ai_worker/core/text_helpers.py`` 의 ``strip_code_fence`` 헬퍼를 검증한다.

이전에는 ``RAGGenerator`` 클래스의 staticmethod 였던 부분이 도메인 분해에
따라 함수형 모듈로 이전됐다.
"""

from ai_worker.core.text_helpers import strip_code_fence
from ai_worker.domains.rag.prompt_builder import (
  SUMMARY_SYSTEM_PROMPT,
  build_summary_user_prompt,
)


class TestSummarySystemPrompt:
  def test_system_prompt_has_role_rule_task_output_sections(self) -> None:
    for header in ("# Role", "# Rule", "# Task", "# Output Format"):
      assert header in SUMMARY_SYSTEM_PROMPT, f"missing section: {header}"

  def test_system_prompt_forbids_out_of_scope_retention(self) -> None:
    # Rule must explicitly instruct to drop non-medical noise.
    assert "의료" in SUMMARY_SYSTEM_PROMPT
    assert "제외" in SUMMARY_SYSTEM_PROMPT or "무관" in SUMMARY_SYSTEM_PROMPT

  def test_system_prompt_preserves_medication_facts(self) -> None:
    # Drug names / symptoms / allergies must be preserved verbatim.
    assert "약품명" in SUMMARY_SYSTEM_PROMPT
    assert "알레르기" in SUMMARY_SYSTEM_PROMPT

  def test_system_prompt_caps_length(self) -> None:
    assert "300자" in SUMMARY_SYSTEM_PROMPT

  def test_system_prompt_requires_markdown_output(self) -> None:
    """The summary must be persisted as Markdown, so the prompt must ask for it."""
    assert "Markdown" in SUMMARY_SYSTEM_PROMPT or "마크다운" in SUMMARY_SYSTEM_PROMPT

  def test_system_prompt_forbids_code_fence_wrapping(self) -> None:
    """The LLM must emit markdown body directly, not wrapped in a ``` fence."""
    assert "코드블록" in SUMMARY_SYSTEM_PROMPT

  def test_system_prompt_declares_section_headers(self) -> None:
    """Downstream rendering depends on the '## <section>' skeleton being present."""
    for header in ("## 한 줄 요약", "## 복용 중인 약", "## 증상", "## 알레르기"):
      assert header in SUMMARY_SYSTEM_PROMPT, f"missing header spec: {header}"


class TestSummaryUserPrompt:
  def test_user_prompt_includes_prev_summary_when_present(self) -> None:
    messages = [
      {"role": "user", "content": "타이레놀 복용 중"},
      {"role": "assistant", "content": "타이레놀은 하루 최대 4g..."},
    ]
    rendered = build_summary_user_prompt(
      prev_summary="사용자는 편두통으로 타이레놀 복용 중.",
      messages=messages,
    )
    assert "[이전 요약]" in rendered
    assert "편두통으로 타이레놀 복용 중" in rendered
    assert "[새 대화 로그]" in rendered

  def test_user_prompt_marks_prev_summary_absent(self) -> None:
    rendered = build_summary_user_prompt(
      prev_summary=None,
      messages=[
        {"role": "user", "content": "타이레놀 복용 중"},
        {"role": "assistant", "content": "타이레놀 안내..."},
      ],
    )
    assert "[이전 요약]" in rendered
    assert "(없음)" in rendered

  def test_user_prompt_treats_blank_prev_summary_as_absent(self) -> None:
    rendered = build_summary_user_prompt(
      prev_summary="   ",
      messages=[
        {"role": "user", "content": "타이레놀 복용 중"},
        {"role": "assistant", "content": "타이레놀 안내..."},
      ],
    )
    assert "(없음)" in rendered

  def test_user_prompt_renders_messages_in_order(self) -> None:
    messages = [
      {"role": "user", "content": "첫 질문"},
      {"role": "assistant", "content": "첫 답변"},
      {"role": "user", "content": "두번째 질문"},
      {"role": "assistant", "content": "두번째 답변"},
    ]
    rendered = build_summary_user_prompt(prev_summary=None, messages=messages)
    idx = [rendered.find(text) for text in ("첫 질문", "첫 답변", "두번째 질문", "두번째 답변")]
    assert all(i >= 0 for i in idx)
    assert idx == sorted(idx), "messages must be rendered in chronological order"

  def test_user_prompt_labels_roles_distinctly(self) -> None:
    rendered = build_summary_user_prompt(
      prev_summary=None,
      messages=[
        {"role": "user", "content": "질문입니다"},
        {"role": "assistant", "content": "답변입니다"},
      ],
    )
    assert "USER" in rendered or "사용자" in rendered
    assert "ASSISTANT" in rendered or "AI" in rendered or "약사" in rendered


class TestStripCodeFence:
  """Defensive fence-stripping for markdown summary persistence."""

  def test_leaves_plain_markdown_intact(self) -> None:
    body = "## 한 줄 요약\n사용자는 타이레놀 복용 중."
    assert strip_code_fence(body) == body

  def test_strips_generic_triple_backtick_fence(self) -> None:
    raw = "```\n## 한 줄 요약\n사용자는 타이레놀 복용 중.\n```"
    assert strip_code_fence(raw) == "## 한 줄 요약\n사용자는 타이레놀 복용 중."

  def test_strips_markdown_labelled_fence(self) -> None:
    raw = "```markdown\n## 한 줄 요약\n본문.\n```"
    assert strip_code_fence(raw) == "## 한 줄 요약\n본문."

  def test_handles_trailing_whitespace_around_fence(self) -> None:
    raw = "   ```\n본문만\n```   \n"
    assert strip_code_fence(raw) == "본문만"
