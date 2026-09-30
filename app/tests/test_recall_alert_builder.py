"""RecallAlertBuilder 단위 테스트 (Phase 7 — §A.5.2).

검증 포인트:
- ``build_alert`` 가 sale_stop_yn=Y 1건 → severity="critical", 본문에 "즉시 복용을 중단" 포함.
- ``build_alert`` 가 sale_stop_yn=N 1건 → severity="advisory", 본문에 "즉시 사용 중단은 필요하지 않습니다" 포함.
- ``build_alert([])`` → ``None`` 반환 (응답에 ``recall_alert: null``).
- 동일 ITEM_SEQ 2 사유 (시드 §8) → ``items`` 길이 2, ``recall_command_date`` 최신순 정렬.
- mixed severity (Y 1 + N 1) → 전체 severity="critical" (Y 우선).

외부 호출 X — pure function 빌더의 입력→출력 변환만 검증.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# ── 시드 row fixtures ────────────────────────────────────────────────


@pytest.fixture
def critical_row() -> Any:
  """sale_stop_yn=Y — 시드 §1 (NDMA 데모라니티딘)."""
  return MagicMock(
    item_seq="202504001",
    product_name="데모라니티딘정150밀리그램",
    entrps_name="(주)데모제약",
    recall_reason="N-니트로소디메틸아민(NDMA) 검출",
    recall_command_date="20260428",
    sale_stop_yn="Y",
  )


@pytest.fixture
def advisory_row() -> Any:
  """sale_stop_yn=N — 시드 §3 (자율회수 데이오웬크림)."""
  return MagicMock(
    item_seq="202504006",
    product_name="데이오웬크림0.05%(데소나이드)",
    entrps_name="데이약사주식회사",
    recall_reason="1차 포장 표시사항 오기",
    recall_command_date="20260420",
    sale_stop_yn="N",
  )


# ── build_alert: critical 분기 (sale_stop_yn=Y) ──────────────────────


class TestBuildAlertCriticalSingle:
  def test_single_y_row_yields_critical_severity(self, critical_row: Any) -> None:
    """sale_stop_yn=Y 1건 → severity=critical, header/body 키워드 포함."""
    from app.services.recall_alert_builder import build_alert

    alert = build_alert([critical_row])

    assert alert is not None
    assert alert.severity == "critical"
    assert "회수·판매중지" in alert.header
    assert "즉시 복용을 중단" in alert.body
    assert len(alert.items) == 1
    assert alert.items[0].item_seq == "202504001"
    assert alert.items[0].sale_stop_yn == "Y"


# ── build_alert: advisory 분기 (sale_stop_yn=N) ──────────────────────


class TestBuildAlertAdvisorySingle:
  def test_single_n_row_yields_advisory_severity(self, advisory_row: Any) -> None:
    """sale_stop_yn=N 1건 → severity=advisory, 본문에 부드러운 톤."""
    from app.services.recall_alert_builder import build_alert

    alert = build_alert([advisory_row])

    assert alert is not None
    assert alert.severity == "advisory"
    assert "회수 안내" in alert.header
    assert "즉시 사용 중단은 필요하지 않습니다" in alert.body
    assert len(alert.items) == 1
    assert alert.items[0].sale_stop_yn == "N"


# ── build_alert: 매칭 0건 ────────────────────────────────────────────


class TestBuildAlertEmpty:
  def test_empty_rows_returns_none(self) -> None:
    """매칭 0건 → None — 응답에 recall_alert 키가 ``null`` 로 직렬화."""
    from app.services.recall_alert_builder import build_alert

    assert build_alert([]) is None


# ── build_alert: 다건 + 정렬 (시드 §8) ──────────────────────────────


class TestBuildAlertMultipleRowsSameItemSeq:
  def test_two_reasons_same_item_seq_sorted_by_date_descending(self) -> None:
    """같은 item_seq 2 사유 → items 길이 2, 최신 recall_command_date 가 첫 항목."""
    from app.services.recall_alert_builder import build_alert

    older = MagicMock(
      item_seq="202504018",
      product_name="오미크론케어연고",
      entrps_name="(주)오미크론바이오",
      recall_reason="포장재 불량(코팅 벗겨짐)",
      recall_command_date="20260326",
      sale_stop_yn="N",
    )
    newer = MagicMock(
      item_seq="202504018",
      product_name="오미크론케어연고",
      entrps_name="(주)오미크론바이오",
      recall_reason="안정성시험 일부항목(성상)",
      recall_command_date="20260330",
      sale_stop_yn="N",
    )
    # 입력 순서를 일부러 뒤섞어도 build_alert 가 최신순 재정렬해야 한다.
    alert = build_alert([older, newer])

    assert alert is not None
    assert len(alert.items) == 2
    assert alert.items[0].recall_command_date == "20260330"
    assert alert.items[1].recall_command_date == "20260326"


# ── build_alert: mixed severity (Y 우선) — §D.5 시나리오 ─────────────


class TestBuildAlertMixedSeverity:
  def test_mixed_y_and_n_yields_critical(self, critical_row: Any, advisory_row: Any) -> None:
    """Y 1건 + N 1건 → severity=critical (Y 1건이라도 있으면 우선).

    §D.5 직접입력 mixed 시연 시나리오의 핵심 회귀 가드.
    """
    from app.services.recall_alert_builder import build_alert

    # 입력 순서를 N→Y 로 뒤집어도 결과 severity 가 critical 이어야 한다.
    alert = build_alert([advisory_row, critical_row])

    assert alert is not None
    assert alert.severity == "critical"
    assert len(alert.items) == 2
