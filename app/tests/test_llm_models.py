"""용도별 LLM 모델 배치를 잠근다 (v2.0 재배포 PLAN S1 · 결정 ⓝ).

🔑 왜 두 모델로 나누나
무료 등급 한도가 **모델별**이다(AI Studio 실측 2026-10-16: Flash Lite RPD 500, Flash RPD 20).
챗봇 한 턴은 재작성 1회 + 응답 1회라, 둘을 서로 다른 모델에 두면 각자 500회씩 써서
하루 약 500턴까지 버틴다. 같은 모델에 두면 250턴에서 막힌다.
"""

from app.core import llm_models

_LIGHT = "gemini-3.1-flash-lite"  # 짧은 구조화 출력 — 재작성·매칭·요약
_LONG = "gemini-3.5-flash-lite"  # 긴 생성 — 챗봇 응답·생활 가이드


# ── 용도별 배치 ────────────────────────────────────────────────────────
class TestModelAssignment:
  """어느 용도가 어느 모델인가."""

  def test_light_tasks_use_light_model(self) -> None:
    """재작성·OCR 매칭·세션 요약은 가벼운 쪽."""
    assert llm_models.QUERY_REWRITER_MODEL == _LIGHT
    assert llm_models.MEDICINE_MATCHER_MODEL == _LIGHT
    assert llm_models.SESSION_SUMMARY_MODEL == _LIGHT

  def test_long_generation_uses_other_model(self) -> None:
    """챗봇 응답·생활 가이드는 다른 모델 — 한도를 나눠 쓴다."""
    assert llm_models.RAG_RESPONSE_MODEL == _LONG
    assert llm_models.LIFESTYLE_GUIDE_MODEL == _LONG

  def test_chat_turn_spans_two_models(self) -> None:
    """한 턴의 두 호출이 서로 다른 모델이어야 한도가 나뉜다."""
    assert llm_models.QUERY_REWRITER_MODEL != llm_models.RAG_RESPONSE_MODEL


# ── 옛 제공자 잔재 ─────────────────────────────────────────────────────
class TestNoLegacyModels:
  """모델 문자열 전수 — 하나라도 옛 제공자 이름이면 그 경로는 Gemini 엔드포인트에서 404 다."""

  def test_every_model_constant_is_flash_lite(self) -> None:
    """모듈의 모든 ``*_MODEL`` 상수가 두 Flash Lite 중 하나다."""
    models = {name: value for name, value in vars(llm_models).items() if name.endswith("_MODEL")}
    assert len(models) >= 5, f"모델 상수가 {len(models)}개 — 대상이 줄었다(이름 규칙이 바뀌었나)"
    assert set(models.values()) <= {_LIGHT, _LONG}, models
