"""Unit tests for LifestyleGuide, DailySymptomLog models and Challenge extensions.

Tests verify:
- LifestyleGuide model has required fields and GuideCategory enum is correct.
- DailySymptomLog model has required fields.
- Challenge model has new lifestyle-guide-related fields.

All tests are intentionally RED until the models are implemented.
"""

from app.models.challenge import Challenge
from app.models.daily_symptom_log import DailySymptomLog
from app.models.lifestyle_guide import GuideCategory, LifestyleGuide

# ── GuideCategory enum ─────────────────────────────────────────────────────


def test_guide_category_has_five_values() -> None:
  """GuideCategory enum은 5개의 카테고리를 가져야 한다."""
  assert len(GuideCategory) == 5


def test_guide_category_values() -> None:
  """GuideCategory enum 값이 계획된 5개 카테고리와 일치해야 한다."""
  assert GuideCategory.DIET == "diet"
  assert GuideCategory.SLEEP == "sleep"
  assert GuideCategory.EXERCISE == "exercise"
  assert GuideCategory.SYMPTOM == "symptom"
  assert GuideCategory.INTERACTION == "interaction"


# ── LifestyleGuide model ───────────────────────────────────────────────────


def test_lifestyle_guide_table_name() -> None:
  """LifestyleGuide 모델의 테이블 이름은 lifestyle_guides 이어야 한다."""
  assert LifestyleGuide.Meta.table == "lifestyle_guides"


def test_lifestyle_guide_has_required_fields() -> None:
  """LifestyleGuide 모델은 필수 필드를 모두 가져야 한다."""
  fields = LifestyleGuide._meta.fields_map
  assert "id" in fields
  assert "profile" in LifestyleGuide._meta.fk_fields
  assert "content" in fields
  assert "medication_snapshot" in fields
  assert "created_at" in fields


# ── DailySymptomLog model ──────────────────────────────────────────────────


def test_daily_symptom_log_table_name() -> None:
  """DailySymptomLog 모델의 테이블 이름은 daily_symptom_logs 이어야 한다."""
  assert DailySymptomLog.Meta.table == "daily_symptom_logs"


def test_daily_symptom_log_has_required_fields() -> None:
  """DailySymptomLog 모델은 필수 필드를 모두 가져야 한다."""
  fields = DailySymptomLog._meta.fields_map
  assert "id" in fields
  assert "profile" in DailySymptomLog._meta.fk_fields
  assert "log_date" in fields
  assert "symptoms" in fields
  assert "created_at" in fields


# ── Challenge model extensions ─────────────────────────────────────────────


def test_challenge_has_guide_fk() -> None:
  """Challenge 모델은 nullable guide FK를 가져야 한다."""
  assert "guide" in Challenge._meta.fk_fields


def test_challenge_has_category_field() -> None:
  """Challenge 모델은 lifestyle 카테고리 필드를 가져야 한다."""
  fields = Challenge._meta.fields_map
  assert "category" in fields


def test_challenge_has_is_active_field() -> None:
  """Challenge 모델은 is_active(챌린지 진행 여부) 필드를 가져야 한다."""
  fields = Challenge._meta.fields_map
  assert "is_active" in fields


def test_challenge_has_started_at_field() -> None:
  """Challenge 모델은 started_at(챌린지 시작 일시) 필드를 가져야 한다."""
  fields = Challenge._meta.fields_map
  assert "started_at" in fields


def test_challenge_has_completed_at_field() -> None:
  """Challenge 모델은 completed_at(챌린지 완료 일시) 필드를 가져야 한다."""
  fields = Challenge._meta.fields_map
  assert "completed_at" in fields


def test_challenge_is_active_default_is_false() -> None:
  """Challenge.is_active 기본값은 False여야 한다."""
  field = Challenge._meta.fields_map.get("is_active")
  assert field is not None
  assert field.default is False
