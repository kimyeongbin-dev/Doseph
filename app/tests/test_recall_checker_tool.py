"""Recall checker tool 단위 테스트 (Phase 7 Step 5).

검증 포인트:
- check_user_medications_recall(profile_id):
    1. 사용자 medications 조회
    2. medicine_info → item_seq 셋 추출
    3. drug_recalls.find_by_item_seqs 매칭
    4. fallback: product_name ILIKE (S7)
    5. 응답 dict 영어 snake_case
- check_manufacturer_recalls(profile_id, manufacturer=None):
    1. manufacturer 인자 있으면 그것만 정규화 매칭
    2. 없으면 사용자 복용약의 entp_name 셋 자동 조회
    3. 모든 row 정규화 후 entrps_name_normalized 매칭
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest


@pytest.fixture
def profile_id() -> UUID:
  return uuid4()


def _recall(item_seq: str, product_name: str, entrps: str, reason: str, date: str) -> MagicMock:
  """Build a fake DrugRecall row."""
  row = MagicMock()
  row.item_seq = item_seq
  row.product_name = product_name
  row.entrps_name = entrps
  row.recall_reason = reason
  row.recall_command_date = date
  row.sale_stop_yn = "N"
  return row


# ── Q1: check_user_medications_recall ────────────────────────────────


class TestCheckUserMedicationsRecall:
  @pytest.mark.asyncio
  async def test_hit_returns_recall_list(self, profile_id: UUID) -> None:
    """복용약과 회수 약이 매칭되면 회수 정보 반환."""
    from app.services.tools.recalls.checker import check_user_medications_recall

    med = MagicMock(medicine_name="마데카솔케어연고")
    recalls = [_recall("200903973", "마데카솔케어연고", "동국제약(주)", "포장재 불량", "20260401")]

    med_repo = MagicMock(get_all_by_profile=AsyncMock(return_value=[med]))
    recall_repo = MagicMock(find_match=AsyncMock(return_value=recalls))

    result = await check_user_medications_recall(
      profile_id=profile_id,
      medication_repository=med_repo,
      drug_recall_repository=recall_repo,
    )

    assert result["matched"] is True
    assert len(result["recalls"]) == 1
    first = result["recalls"][0]
    assert first["item_seq"] == "200903973"
    assert first["product_name"] == "마데카솔케어연고"
    assert first["entrps_name"] == "동국제약(주)"
    assert first["recall_reason"] == "포장재 불량"
    assert first["recall_command_date"] == "20260401"

  @pytest.mark.asyncio
  async def test_miss_returns_empty(self, profile_id: UUID) -> None:
    """매칭 결과 0건이면 matched=False, recalls=[]."""
    from app.services.tools.recalls.checker import check_user_medications_recall

    med = MagicMock(medicine_name="벨메텍정20밀리그램")
    med_repo = MagicMock(get_all_by_profile=AsyncMock(return_value=[med]))
    recall_repo = MagicMock(find_match=AsyncMock(return_value=[]))

    result = await check_user_medications_recall(
      profile_id=profile_id,
      medication_repository=med_repo,
      drug_recall_repository=recall_repo,
    )

    assert result["matched"] is False
    assert result["recalls"] == []

  @pytest.mark.asyncio
  async def test_no_medications_returns_empty(self, profile_id: UUID) -> None:
    """사용자가 등록한 약이 0건이면 즉시 빈 결과."""
    from app.services.tools.recalls.checker import check_user_medications_recall

    med_repo = MagicMock(get_all_by_profile=AsyncMock(return_value=[]))
    recall_repo = MagicMock(find_match=AsyncMock())

    result = await check_user_medications_recall(
      profile_id=profile_id,
      medication_repository=med_repo,
      drug_recall_repository=recall_repo,
    )

    assert result["matched"] is False
    assert result["recalls"] == []
    recall_repo.find_match.assert_not_called()

  @pytest.mark.asyncio
  async def test_dedup_same_item_seq_multiple_reasons(self, profile_id: UUID) -> None:
    """같은 약이 여러 회수 사유로 등장하면 모두 응답에 포함 (중복 제거 안 함)."""
    from app.services.tools.recalls.checker import check_user_medications_recall

    med = MagicMock(medicine_name="아무약")
    recalls = [
      _recall("X", "아무약", "Y", "사유1", "20260101"),
      _recall("X", "아무약", "Y", "사유2", "20260102"),
    ]
    med_repo = MagicMock(get_all_by_profile=AsyncMock(return_value=[med]))
    recall_repo = MagicMock(find_match=AsyncMock(return_value=recalls))

    result = await check_user_medications_recall(
      profile_id=profile_id,
      medication_repository=med_repo,
      drug_recall_repository=recall_repo,
    )

    reasons = [r["recall_reason"] for r in result["recalls"]]
    assert reasons == ["사유1", "사유2"]


# ── Q2: check_manufacturer_recalls ───────────────────────────────────


class TestCheckManufacturerRecalls:
  @pytest.mark.asyncio
  async def test_explicit_manufacturer_arg(self, profile_id: UUID) -> None:
    """manufacturer 인자가 있으면 그것 한 개만 매칭."""
    from app.services.tools.recalls.checker import check_manufacturer_recalls

    recalls = [_recall("X", "Y", "동국제약(주)", "사유", "20260401")]

    med_repo = MagicMock()
    recall_repo = MagicMock(find_by_manufacturers=AsyncMock(return_value=recalls))

    result = await check_manufacturer_recalls(
      profile_id=profile_id,
      manufacturer="동국제약(주)",
      medication_repository=med_repo,
      drug_recall_repository=recall_repo,
    )

    assert result["matched"] is True
    assert len(result["recalls"]) == 1
    # 입력 인자가 그대로 전달됨 (Repository 가 정규화)
    called_args = recall_repo.find_by_manufacturers.await_args.args[0]
    assert "동국제약(주)" in set(called_args)

  @pytest.mark.asyncio
  async def test_no_manufacturer_arg_uses_user_medications(self, profile_id: UUID) -> None:
    """인자가 없으면 사용자 복용약의 medicine_info.entp_name 셋을 자동 조회."""
    from app.services.tools.recalls.checker import check_manufacturer_recalls

    med = MagicMock(medicine_name="마데카솔케어연고")
    med_repo = MagicMock(
      get_all_by_profile=AsyncMock(return_value=[med]),
    )

    # checker 가 medicine_info 에서 entp_name 을 추출하도록 위임
    async def fake_resolve(_profile_id: UUID) -> set[str]:
      return {"동국제약(주)", "(주)종근당"}

    recalls = [_recall("X", "Y", "동국제약(주)", "사유", "20260401")]
    recall_repo = MagicMock(find_by_manufacturers=AsyncMock(return_value=recalls))

    # checker 가 노출하는 manufacturer 해상도 함수를 monkeypatch
    from app.services.tools.recalls import checker as checker_mod

    original = checker_mod.resolve_user_manufacturers
    checker_mod.resolve_user_manufacturers = fake_resolve  # type: ignore[assignment]
    try:
      result = await check_manufacturer_recalls(
        profile_id=profile_id,
        manufacturer=None,
        medication_repository=med_repo,
        drug_recall_repository=recall_repo,
      )
    finally:
      checker_mod.resolve_user_manufacturers = original

    assert result["matched"] is True
    called_args = recall_repo.find_by_manufacturers.await_args.args[0]
    assert set(called_args) == {"동국제약(주)", "(주)종근당"}

  @pytest.mark.asyncio
  async def test_empty_set_returns_empty(self, profile_id: UUID) -> None:
    """제조사가 없으면 빈 결과."""
    from app.services.tools.recalls.checker import check_manufacturer_recalls

    recall_repo = MagicMock(find_by_manufacturers=AsyncMock(return_value=[]))
    med_repo = MagicMock()

    result = await check_manufacturer_recalls(
      profile_id=profile_id,
      manufacturer="존재하지않는회사",
      medication_repository=med_repo,
      drug_recall_repository=recall_repo,
    )

    assert result["matched"] is False
    assert result["recalls"] == []


# ── 응답 스키마 일관성 ────────────────────────────────────────────────


class TestResponseSchema:
  @pytest.mark.asyncio
  async def test_response_keys_are_english_snake_case(self, profile_id: UUID) -> None:
    """응답 dict 의 모든 키가 영어 snake_case."""
    from app.services.tools.recalls.checker import check_user_medications_recall

    med = MagicMock(medicine_name="X")
    recalls = [_recall("a", "b", "c", "d", "e")]
    med_repo = MagicMock(get_all_by_profile=AsyncMock(return_value=[med]))
    recall_repo = MagicMock(find_match=AsyncMock(return_value=recalls))

    result = await check_user_medications_recall(
      profile_id=profile_id,
      medication_repository=med_repo,
      drug_recall_repository=recall_repo,
    )

    snake_re = lambda s: s == s.lower() and " " not in s and not any(ord(c) > 127 for c in s)  # noqa: E731
    for top_key in result:
      assert snake_re(top_key), top_key
    for k in result["recalls"][0]:
      assert snake_re(k), k


def _stub() -> Any:
  """Force module import side-effect (avoid lazy stale)."""
  return None
