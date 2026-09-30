"""Recall notification dispatcher 단위 테스트 (Phase 7 Step 7).

검증 포인트:
- send_recall_alert: 알림 메시지 생성 + metadata 키 일관성
- dedup: 동일 (item_seq, recall_command_date, recall_reason, medication_id) 재호출 시 skip
- 세션 미존재 시 skip + warning
- 메시지 템플릿: "[안전 알림] {약품}이(가) 식약처에서 {사유}로 {날짜} 회수되었습니다."
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _recall(item_seq: str = "200903973") -> Any:
  row = MagicMock()
  row.item_seq = item_seq
  row.product_name = "마데카솔케어연고"
  row.entrps_name = "동국제약(주)"
  row.recall_reason = "포장재 불량(코팅 벗겨짐)"
  row.recall_command_date = "20260401"
  row.sale_stop_yn = "N"
  return row


def _medication(name: str = "마데카솔케어연고") -> Any:
  med = MagicMock()
  med.id = uuid4()
  med.medicine_name = name
  return med


# ── send_recall_alert ────────────────────────────────────────────────


class TestSendRecallAlert:
  @pytest.mark.asyncio
  async def test_inserts_message_with_metadata(self) -> None:
    from app.services import recall_notification_service as svc

    profile_id = uuid4()
    recall = _recall()
    medication = _medication()

    with (
      patch.object(svc, "_already_notified", new=AsyncMock(return_value=False)),
      patch.object(svc, "_resolve_target_session_id", new=AsyncMock(return_value=uuid4())),
      patch.object(svc.ChatMessage, "create", new=AsyncMock()) as create,
    ):
      await svc.send_recall_alert(profile_id=profile_id, recall=recall, medication=medication)

    create.assert_awaited_once()
    kw = create.await_args.kwargs
    assert kw["sender_type"] == svc.SenderType.ASSISTANT
    # 메시지 내용 검증
    assert "마데카솔케어연고" in kw["content"]
    assert "포장재 불량(코팅 벗겨짐)" in kw["content"]
    assert "2026-04-01" in kw["content"]
    # metadata 일관성
    meta = kw["metadata"]
    assert meta["kind"] == svc.RECALL_ALERT_KIND
    assert meta["recall_item_seq"] == "200903973"
    assert meta["recall_command_date"] == "20260401"
    assert meta["medication_id"] == str(medication.id)

  @pytest.mark.asyncio
  async def test_dedup_returns_none(self) -> None:
    """이미 보낸 알림이면 None 반환 + ChatMessage 생성 호출 X."""
    from app.services import recall_notification_service as svc

    with (
      patch.object(svc, "_already_notified", new=AsyncMock(return_value=True)),
      patch.object(svc.ChatMessage, "create", new=AsyncMock()) as create,
    ):
      result = await svc.send_recall_alert(profile_id=uuid4(), recall=_recall(), medication=_medication())

    assert result is None
    create.assert_not_called()

  @pytest.mark.asyncio
  async def test_no_session_skips(self) -> None:
    """활성 chat session 이 없으면 skip + None."""
    from app.services import recall_notification_service as svc

    with (
      patch.object(svc, "_already_notified", new=AsyncMock(return_value=False)),
      patch.object(svc, "_resolve_target_session_id", new=AsyncMock(return_value=None)),
      patch.object(svc.ChatMessage, "create", new=AsyncMock()) as create,
    ):
      result = await svc.send_recall_alert(profile_id=uuid4(), recall=_recall(), medication=_medication())

    assert result is None
    create.assert_not_called()


# ── F3 hook helper (PLAN §16.3.2) ─────────────────────────────────────


class TestCheckAndAlertOnMedicationSave:
  """공용 후크 — `medication_service` / `ocr_service` 양쪽에서 호출되는 단일 진입점."""

  @pytest.mark.asyncio
  async def test_returns_none_when_no_match(self) -> None:
    """find_match 가 빈 리스트면 None 반환 + send_recall_alert 호출 X."""
    from app.services import recall_notification_service as svc

    repo = MagicMock(find_match=AsyncMock(return_value=[]))
    med = _medication()

    with patch.object(svc, "send_recall_alert", new=AsyncMock()) as send:
      result = await svc.check_and_alert_on_medication_save(med, drug_recall_repo=repo)

    assert result is None
    send.assert_not_called()

  @pytest.mark.asyncio
  async def test_returns_first_match_and_dispatches_per_recall(self) -> None:
    """매칭 row 가 N건이면 send_recall_alert 를 N번 호출하고 첫 row 반환."""
    from app.services import recall_notification_service as svc

    recalls = [_recall("X"), _recall("Y"), _recall("Z")]
    repo = MagicMock(find_match=AsyncMock(return_value=recalls))
    med = _medication()

    with patch.object(svc, "send_recall_alert", new=AsyncMock()) as send:
      result = await svc.check_and_alert_on_medication_save(med, drug_recall_repo=repo)

    assert result is recalls[0]
    assert send.await_count == 3
    # 모든 호출이 동일 medication + profile_id 를 사용했는지 확인
    for call in send.await_args_list:
      assert call.kwargs["medication"] is med
      assert call.kwargs["profile_id"] == med.profile_id

  @pytest.mark.asyncio
  async def test_uses_default_repo_when_none(self) -> None:
    """drug_recall_repo=None 이면 기본 ``DrugRecallRepository()`` 인스턴스 사용."""
    from app.services import recall_notification_service as svc

    med = _medication()

    with (
      patch.object(svc, "DrugRecallRepository") as repo_cls,
      patch.object(svc, "send_recall_alert", new=AsyncMock()),
    ):
      repo_cls.return_value.find_match = AsyncMock(return_value=[])
      result = await svc.check_and_alert_on_medication_save(med)

    assert result is None
    repo_cls.assert_called_once_with()

  @pytest.mark.asyncio
  async def test_propagates_repo_errors(self) -> None:
    """헬퍼는 의도적으로 예외를 raise — 격리는 호출자(서비스)의 책임."""
    from app.services import recall_notification_service as svc

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
      msg = "db down"
      raise RuntimeError(msg)

    repo = MagicMock(find_match=AsyncMock(side_effect=boom))
    med = _medication()

    with pytest.raises(RuntimeError, match="db down"):
      await svc.check_and_alert_on_medication_save(med, drug_recall_repo=repo)
