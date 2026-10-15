"""LLM 클라이언트가 **Gemini 의 OpenAI 호환 엔드포인트**로 가는지 잠근다 (v2.0 재배포 PLAN S1).

🔑 무엇을 잠그나
- 주소는 ``app.core.llm_client.LLM_BASE_URL`` 한 곳 — 경계 테스트들도 이 상수로 가로챈다.
- 키는 ``GEMINI_API_KEY`` 하나 — ``OPENAI_API_KEY`` 는 설정에서 사라진다(옛 제공자 경로가 조용히 남지 않게).
- 생활 가이드 잡은 키가 없으면 **예외**다(다른 경로의 «None → fallback» 과 다르다 — 지금 동작 그대로).
"""

import pytest

from ai_worker.core.config import Config as WorkerConfig
from ai_worker.domains.lifestyle import jobs as lifestyle_jobs
from app.core.config import Config as AppConfig
from app.core.llm_client import LLM_BASE_URL, build_llm_client

_GEMINI_OPENAI_COMPAT = "https://generativelanguage.googleapis.com/v1beta/openai/"
_FAKE_KEY = "FAKE_gemini_key"


# ── 주소 ───────────────────────────────────────────────────────────────
class TestBaseUrl:
  """클라이언트가 가는 곳."""

  def test_base_url_is_gemini_openai_compatible_endpoint(self) -> None:
    """주소 상수는 Gemini 의 OpenAI 호환 엔드포인트다."""
    assert LLM_BASE_URL == _GEMINI_OPENAI_COMPAT

  def test_built_client_targets_that_base_url(self) -> None:
    """만든 클라이언트가 실제로 그 주소를 쓴다 — 상수만 바꾸고 생성에 안 넘기는 실수를 막는다."""
    client = build_llm_client(_FAKE_KEY)
    assert str(client.base_url) == LLM_BASE_URL


# ── 키 이름 ────────────────────────────────────────────────────────────
class TestKeyName:
  """설정이 읽는 키."""

  @pytest.mark.parametrize("settings_cls", [AppConfig, WorkerConfig], ids=["app", "ai_worker"])
  def test_settings_define_gemini_key(self, settings_cls: type) -> None:
    """앱·워커 설정 모두 ``GEMINI_API_KEY`` 를 갖는다."""
    assert "GEMINI_API_KEY" in settings_cls.model_fields

  @pytest.mark.parametrize("settings_cls", [AppConfig, WorkerConfig], ids=["app", "ai_worker"])
  def test_settings_drop_openai_key(self, settings_cls: type) -> None:
    """``OPENAI_API_KEY`` 는 없다 — 남아 있으면 옛 키로 도는 경로를 아무도 못 본다."""
    assert "OPENAI_API_KEY" not in settings_cls.model_fields


# ── 생활 가이드 잡 ─────────────────────────────────────────────────────
class TestLifestyleJobClient:
  """``lifestyle.jobs`` 는 자체 키 판정을 한다 — 같은 키·같은 주소인지 따로 본다."""

  def test_builds_gemini_client_from_gemini_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """``GEMINI_API_KEY`` 가 있으면 Gemini 주소의 클라이언트."""
    monkeypatch.setenv("GEMINI_API_KEY", _FAKE_KEY)
    client = lifestyle_jobs._build_openai_client()
    assert str(client.base_url) == LLM_BASE_URL

  def test_raises_when_gemini_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """키가 없으면 예외 — 메시지가 **어느 키**가 없는지 말한다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
      lifestyle_jobs._build_openai_client()
