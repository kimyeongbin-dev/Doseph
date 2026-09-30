"""DrugRecallRepository 단위 테스트 (Phase 7 Step 3).

검증 포인트:
- bulk_upsert: 복합 UNIQUE 키 기반 다중 row 적재 (§14.5 발견 #1)
- find_by_item_seqs: Q1 매칭, 동일 item_seq 다건 반환
- find_by_manufacturers: 입력 names 를 normalize_company_name 으로
  정규화 후 entrps_name_normalized 매칭 (§14.5 발견 #2)
- diff_new_recalls: 신규 row 만 반환
- find_match: item_seq 1순위 → product_name ILIKE 2순위 (S7 fallback)

Tortoise ORM 의 메서드 (`update_or_create`, `filter`) 를 mock 으로 교체해
DB 연결 없이 검증한다 (CI 비용 0).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def repo() -> Any:
  """Return a fresh repository instance."""
  from app.repositories.drug_recall_repository import DrugRecallRepository

  return DrugRecallRepository()


# ── bulk_upsert: 복합 UNIQUE 키 기반 ──────────────────────────────────


class TestBulkUpsert:
  """복합 UNIQUE 키 (item_seq, recall_command_date, recall_reason) 기반 UPSERT."""

  @pytest.mark.asyncio
  async def test_bulk_upsert_inserts_new_rows(self, repo: Any) -> None:
    """모든 row 가 신규일 때 inserted 카운트가 정확해야 한다."""
    items = [
      {
        "item_seq": "200903973",
        "product_name": "마데카솔케어연고",
        "entrps_name": "동국제약(주)",
        "recall_reason": "포장재 불량(코팅 벗겨짐)",
        "recall_command_date": "20260401",
        "sale_stop_yn": "N",
        "is_hospital_only": False,
        "is_non_drug": False,
      },
    ]

    with patch("app.repositories.drug_recall_repository.DrugRecall.update_or_create", new=AsyncMock()) as m:
      m.return_value = (MagicMock(), True)
      stats = await repo.bulk_upsert(items)

    assert stats == {"inserted": 1, "updated": 0}
    m.assert_awaited_once()

  @pytest.mark.asyncio
  async def test_bulk_upsert_handles_same_item_seq_multiple_rows(self, repo: Any) -> None:
    """🔴 동일 item_seq 가 다중 회수 사유로 등장해도 모두 적재되어야 한다 (§14.5.1).

    시드 §14.5.1 의 `202007244` 3건이 복합 UNIQUE 덕분에 충돌 없이 적재.
    """
    items = [
      {
        "item_seq": "202007244",
        "product_name": "마데바텔넥치약",
        "entrps_name": "우리생활건강",
        "recall_reason": "품질부적합 우려(마데바텔넥치약)",
        "recall_command_date": "20260420",
        "sale_stop_yn": "N",
      },
      {
        "item_seq": "202007244",
        "product_name": "프로폴리브러쉬치약",
        "entrps_name": "우리생활건강",
        "recall_reason": "품질부적합 우려(프로폴리브러쉬치약)",
        "recall_command_date": "20260420",
        "sale_stop_yn": "N",
      },
      {
        "item_seq": "202007244",
        "product_name": "덴탈힐링프로폴치약",
        "entrps_name": "우리생활건강",
        "recall_reason": "품질부적합 우려(덴탈힐링프로폴치약)",
        "recall_command_date": "20260420",
        "sale_stop_yn": "N",
      },
    ]

    with patch("app.repositories.drug_recall_repository.DrugRecall.update_or_create", new=AsyncMock()) as m:
      m.return_value = (MagicMock(), True)
      stats = await repo.bulk_upsert(items)

    assert stats["inserted"] == 3
    assert m.await_count == 3

  @pytest.mark.asyncio
  async def test_bulk_upsert_keys_are_composite(self, repo: Any) -> None:
    """update_or_create 호출 시 복합 키 3개를 매칭 키로 사용해야 한다."""
    items = [
      {
        "item_seq": "200903973",
        "product_name": "마데카솔케어연고",
        "entrps_name": "동국제약(주)",
        "recall_reason": "포장재 불량(코팅 벗겨짐)",
        "recall_command_date": "20260401",
        "sale_stop_yn": "N",
      },
    ]

    with patch("app.repositories.drug_recall_repository.DrugRecall.update_or_create", new=AsyncMock()) as m:
      m.return_value = (MagicMock(), True)
      await repo.bulk_upsert(items)

    kwargs = m.await_args.kwargs
    # 복합 UNIQUE 키 3개가 lookup 으로 전달되어야 한다.
    assert "item_seq" in kwargs
    assert "recall_command_date" in kwargs
    assert "recall_reason" in kwargs
    # 정규화 컬럼은 defaults 에 들어가 자동 채워져야 한다.
    defaults = kwargs.get("defaults", {})
    assert "entrps_name_normalized" in defaults
    assert defaults["entrps_name_normalized"] == "동국제약"

  @pytest.mark.asyncio
  async def test_bulk_upsert_continues_on_error(self, repo: Any) -> None:
    """한 row 가 실패해도 나머지 row 처리는 계속되어야 한다."""
    items = [
      {
        "item_seq": "A",
        "product_name": "A",
        "entrps_name": "X",
        "recall_reason": "r1",
        "recall_command_date": "20260101",
        "sale_stop_yn": "N",
      },
      {
        "item_seq": "B",
        "product_name": "B",
        "entrps_name": "Y",
        "recall_reason": "r2",
        "recall_command_date": "20260102",
        "sale_stop_yn": "N",
      },
    ]

    async def side_effect(*_args: Any, **kwargs: Any) -> tuple[MagicMock, bool]:
      if kwargs.get("item_seq") == "A":
        raise ValueError("boom")
      return MagicMock(), True

    target = "app.repositories.drug_recall_repository.DrugRecall.update_or_create"
    with patch(target, new=AsyncMock(side_effect=side_effect)):
      stats = await repo.bulk_upsert(items)

    assert stats["inserted"] == 1


# ── find_by_item_seqs: Q1 매칭 ────────────────────────────────────────


class TestFindByItemSeqs:
  """Q1 — 사용자 복용약 item_seq 셋 → drug_recalls 매칭."""

  @pytest.mark.asyncio
  async def test_returns_all_recalls_for_each_item_seq(self, repo: Any) -> None:
    """동일 item_seq 다건 회수 row 모두 반환."""
    rows = [
      MagicMock(item_seq="202007244", recall_reason="r1"),
      MagicMock(item_seq="202007244", recall_reason="r2"),
      MagicMock(item_seq="200903973", recall_reason="r3"),
    ]
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=rows)
      m.return_value = qs
      result = await repo.find_by_item_seqs({"202007244", "200903973"})

    assert len(result) == 3
    m.assert_called_once()
    _args, kwargs = m.call_args
    assert "item_seq__in" in kwargs

  @pytest.mark.asyncio
  async def test_empty_set_returns_empty_list(self, repo: Any) -> None:
    """빈 set 입력은 DB 호출 없이 빈 리스트 반환."""
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      result = await repo.find_by_item_seqs(set())

    assert result == []
    m.assert_not_called()


# ── find_by_manufacturers: Q2 매칭 (정규화) ───────────────────────────


class TestFindByManufacturers:
  """🔴 Q2 — 제조사명 정규화 후 entrps_name_normalized 매칭."""

  @pytest.mark.asyncio
  async def test_normalizes_input_before_query(self, repo: Any) -> None:
    """입력 names 가 normalize_company_name 으로 변환된 뒤 매칭에 사용된다."""
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[])
      m.return_value = qs
      await repo.find_by_manufacturers({"동국제약(주)", "(주)한독"})

    _args, kwargs = m.call_args
    normalized_set = kwargs.get("entrps_name_normalized__in")
    assert normalized_set is not None
    assert set(normalized_set) == {"동국제약", "한독"}

  @pytest.mark.asyncio
  async def test_empty_set_returns_empty_list(self, repo: Any) -> None:
    """빈 set 은 DB 호출 없이 빈 리스트."""
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      result = await repo.find_by_manufacturers(set())

    assert result == []
    m.assert_not_called()

  @pytest.mark.asyncio
  async def test_blank_strings_filtered_out(self, repo: Any) -> None:
    """입력 중 빈 문자열·None 은 제거 후 매칭 set 에 포함되지 않는다."""
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[])
      m.return_value = qs
      await repo.find_by_manufacturers({"동국제약(주)", "", "   "})

    _args, kwargs = m.call_args
    normalized_set = set(kwargs["entrps_name_normalized__in"])
    assert normalized_set == {"동국제약"}


# ── diff_new_recalls: 신규 row만 ──────────────────────────────────────


class TestDiffNewRecalls:
  """cron 동기화 후 새로 추가된 row 만 추출."""

  @pytest.mark.asyncio
  async def test_filters_by_created_at_gt(self, repo: Any) -> None:
    """`created_at__gt=since` 필터로 신규 row 만 반환."""
    from datetime import UTC, datetime

    since = datetime(2026, 4, 27, 3, 0, tzinfo=UTC)
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[])
      m.return_value = qs
      await repo.diff_new_recalls(since=since)

    _args, kwargs = m.call_args
    assert kwargs["created_at__gt"] == since


# ── find_match: F3 + cron 매칭 (item_seq 1순위 → ILIKE 2순위) ─────────


class TestFindMatch:
  """🔴 §14.6 S7 fallback — medicine_info 매칭 실패 시 product_name ILIKE."""

  @pytest.mark.asyncio
  async def test_medicine_info_match_takes_priority(self, repo: Any) -> None:
    """medicine_info 에 같은 medicine_name 이 있으면 item_seq 매칭으로 단축."""
    medication = MagicMock(medicine_name="마데카솔케어연고")
    mi = MagicMock(item_seq="200903973")
    recall_rows = [MagicMock(item_seq="200903973")]

    with (
      patch("app.repositories.drug_recall_repository.MedicineInfo.filter") as mi_filter,
      patch("app.repositories.drug_recall_repository.DrugRecall.filter") as dr_filter,
    ):
      mi_qs = MagicMock()
      mi_qs.first = AsyncMock(return_value=mi)
      mi_filter.return_value = mi_qs

      dr_qs = MagicMock()
      dr_qs.all = AsyncMock(return_value=recall_rows)
      dr_filter.return_value = dr_qs

      result = await repo.find_match(medication)

    assert result == recall_rows
    # DrugRecall.filter 는 item_seq__in 으로 한 번만 호출 (ILIKE 분기 없음)
    assert dr_filter.call_count == 1
    kwargs = dr_filter.call_args.kwargs
    assert "item_seq__in" in kwargs

  @pytest.mark.asyncio
  async def test_falls_back_to_product_name_ilike(self, repo: Any) -> None:
    """medicine_info 에 매칭 row 가 없으면 product_name ILIKE fallback."""
    medication = MagicMock(medicine_name="마데카솔케어연고")
    recall_rows = [MagicMock(product_name="마데카솔케어연고")]

    with (
      patch("app.repositories.drug_recall_repository.MedicineInfo.filter") as mi_filter,
      patch("app.repositories.drug_recall_repository.DrugRecall.filter") as dr_filter,
    ):
      mi_qs = MagicMock()
      mi_qs.first = AsyncMock(return_value=None)  # medicine_info 없음
      mi_filter.return_value = mi_qs

      dr_qs = MagicMock()
      dr_qs.all = AsyncMock(return_value=recall_rows)
      dr_filter.return_value = dr_qs

      result = await repo.find_match(medication)

    assert result == recall_rows
    kwargs = dr_filter.call_args.kwargs
    assert "product_name__icontains" in kwargs
    assert kwargs["product_name__icontains"] == "마데카솔케어연고"

  @pytest.mark.asyncio
  async def test_returns_empty_when_both_strategies_miss(self, repo: Any) -> None:
    """medicine_info 미스 + ILIKE 미스 → 빈 리스트."""
    medication = MagicMock(medicine_name="존재하지않는약")

    with (
      patch("app.repositories.drug_recall_repository.MedicineInfo.filter") as mi_filter,
      patch("app.repositories.drug_recall_repository.DrugRecall.filter") as dr_filter,
    ):
      mi_qs = MagicMock()
      mi_qs.first = AsyncMock(return_value=None)
      mi_filter.return_value = mi_qs

      dr_qs = MagicMock()
      dr_qs.all = AsyncMock(return_value=[])
      dr_filter.return_value = dr_qs

      result = await repo.find_match(medication)

    assert result == []

  @pytest.mark.asyncio
  async def test_blank_medicine_name_returns_empty(self, repo: Any) -> None:
    """medicine_name 이 빈 문자열이면 DB 호출 없이 빈 리스트."""
    medication = MagicMock(medicine_name="")

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as dr_filter:
      result = await repo.find_match(medication)

    assert result == []
    dr_filter.assert_not_called()


# ── A.5.1: find_by_item_seq_or_name (단건 등록 매칭) ──────────────────


class TestFindByItemSeqOrName:
  """A.5.1 — 단건 등록 매칭 (item_seq 우선, product_name 정규화 fallback).

  is_non_drug=True / is_hospital_only=True 행은 사전 필터에서 제외되어
  일반 사용자 매칭 결과에 포함되지 않는다.
  """

  @pytest.mark.asyncio
  async def test_match_by_exact_item_seq_returns_seed_section1_row(self, repo: Any) -> None:
    """A.5.1 #1 — item_seq=202504001 → 시드 §1 NDMA 1건."""
    recall = MagicMock(item_seq="202504001", product_name="데모라니티딘정150밀리그램", sale_stop_yn="Y")

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[recall])
      m.return_value = qs
      result = await repo.find_by_item_seq_or_name(item_seq="202504001")

    assert len(result) == 1
    assert result[0].item_seq == "202504001"
    kwargs = m.call_args.kwargs
    assert kwargs.get("item_seq") == "202504001"
    # 일반 사용자 매칭에서 의약외품/병원전용은 항상 제외된다.
    assert kwargs.get("is_non_drug") is False
    assert kwargs.get("is_hospital_only") is False

  @pytest.mark.asyncio
  async def test_match_by_exact_product_name_returns_seed_section2_row(self, repo: Any) -> None:
    """A.5.1 #2 — product_name=테스트솔정4밀리그램(메틸프레드니솔론) → §2 첫 행 1건."""
    recall = MagicMock(
      item_seq="202504003",
      product_name="테스트솔정4밀리그램(메틸프레드니솔론)",
      sale_stop_yn="Y",
    )

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[recall])
      m.return_value = qs
      result = await repo.find_by_item_seq_or_name(product_name="테스트솔정4밀리그램(메틸프레드니솔론)")

    assert len(result) == 1
    assert result[0].item_seq == "202504003"

  @pytest.mark.asyncio
  async def test_returns_all_rows_for_same_item_seq_composite_unique(self, repo: Any) -> None:
    """A.5.1 #3 — item_seq=202504018 → §8 동일 ITEM_SEQ 2 사유 모두 반환."""
    rows = [
      MagicMock(item_seq="202504018", recall_reason="포장재 불량(코팅 벗겨짐)"),
      MagicMock(item_seq="202504018", recall_reason="안정성시험 일부항목(성상)"),
    ]

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=rows)
      m.return_value = qs
      result = await repo.find_by_item_seq_or_name(item_seq="202504018")

    assert len(result) == 2
    reasons = {r.recall_reason for r in result}
    assert reasons == {"포장재 불량(코팅 벗겨짐)", "안정성시험 일부항목(성상)"}

  @pytest.mark.asyncio
  async def test_excludes_non_drug_rows_via_pre_filter(self, repo: Any) -> None:
    """A.5.1 #4 — 의약외품(is_non_drug=True) 매칭 시 사전 필터로 빈 리스트.

    시드 §4 감마손소독제 (item_seq=202504009) — 사용자에겐 노출되면 안 됨.
    """
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[])
      m.return_value = qs
      result = await repo.find_by_item_seq_or_name(item_seq="202504009")

    assert result == []
    kwargs = m.call_args.kwargs
    assert kwargs.get("is_non_drug") is False

  @pytest.mark.asyncio
  async def test_excludes_hospital_only_rows_via_pre_filter(self, repo: Any) -> None:
    """A.5.1 #5 — 병원전용(is_hospital_only=True) 매칭 시 사전 필터로 빈 리스트.

    시드 §5 제타미다졸람주사 (item_seq=202504012) — 일반 사용자 medication 등록
    흐름에서 매칭되어선 안 됨.
    """
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[])
      m.return_value = qs
      result = await repo.find_by_item_seq_or_name(item_seq="202504012")

    assert result == []
    kwargs = m.call_args.kwargs
    assert kwargs.get("is_hospital_only") is False

  @pytest.mark.asyncio
  async def test_normalizes_product_name_with_whitespace_variant(self, repo: Any) -> None:
    """A.5.1 #6 — 공백 변형 product_name 입력 ' 데모라니티딘정 150밀리그램 ' 도 정규화 매칭.

    시드의 PRDUCT='데모라니티딘정150밀리그램' (공백 0). 입력 양 끝/중간 공백을
    normalize_product_name 으로 통일한 뒤 비교해 §1 row 1건 반환.
    """
    target = MagicMock(item_seq="202504001", product_name="데모라니티딘정150밀리그램")
    other = MagicMock(item_seq="999", product_name="다른약품")

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[target, other])
      m.return_value = qs
      result = await repo.find_by_item_seq_or_name(product_name=" 데모라니티딘정 150밀리그램 ")

    # 정규화 후 메모리 비교로 §1 row 만 통과해야 한다.
    assert len(result) == 1
    assert result[0].item_seq == "202504001"


# ── A.5.4 (repo 부분): find_recalls_for_medications (마이페이지 batch) ──


class TestFindRecallsForMedications:
  """A.5.4 (repo) — 등록된 medication N개에 대해 단일 쿼리로 batch 매칭."""

  @pytest.mark.asyncio
  async def test_empty_medications_skips_db_call(self, repo: Any) -> None:
    """meds=[] → DB 호출 없이 빈 dict."""
    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      result = await repo.find_recalls_for_medications([])

    assert result == {}
    m.assert_not_called()

  @pytest.mark.asyncio
  async def test_single_query_for_n_medications_avoids_n_plus_1(self, repo: Any) -> None:
    """N=3 medication → DrugRecall.filter 정확히 1회 호출 (N+1 회피)."""
    from uuid import uuid4

    meds = [
      MagicMock(id=uuid4(), medicine_name="데모라니티딘정150밀리그램"),
      MagicMock(id=uuid4(), medicine_name="테스트솔정4밀리그램(메틸프레드니솔론)"),
      MagicMock(id=uuid4(), medicine_name="이부프로펜정200밀리그램"),
    ]

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[])
      m.return_value = qs
      await repo.find_recalls_for_medications(meds)

    assert m.call_count == 1

  @pytest.mark.asyncio
  async def test_groups_recall_rows_by_medication_id(self, repo: Any) -> None:
    """반환 dict 가 medication_id 키로 매칭 row list 를 그룹핑."""
    from uuid import uuid4

    med1_id = uuid4()
    med2_id = uuid4()
    meds = [
      MagicMock(id=med1_id, medicine_name="데모라니티딘정150밀리그램"),
      MagicMock(id=med2_id, medicine_name="오미크론케어연고"),
    ]
    recall_for_med1 = MagicMock(
      item_seq="202504001",
      product_name="데모라니티딘정150밀리그램",
      recall_reason="NDMA",
    )
    recall_for_med2_a = MagicMock(
      item_seq="202504018",
      product_name="오미크론케어연고",
      recall_reason="포장재 불량(코팅 벗겨짐)",
    )
    recall_for_med2_b = MagicMock(
      item_seq="202504018",
      product_name="오미크론케어연고",
      recall_reason="안정성시험 일부항목(성상)",
    )

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[recall_for_med1, recall_for_med2_a, recall_for_med2_b])
      m.return_value = qs
      result = await repo.find_recalls_for_medications(meds)

    assert med1_id in result
    assert med2_id in result
    assert len(result[med1_id]) == 1
    assert len(result[med2_id]) == 2

  @pytest.mark.asyncio
  async def test_pre_filters_non_drug_and_hospital_only(self, repo: Any) -> None:
    """is_non_drug / is_hospital_only 사전 필터가 batch 쿼리에도 적용된다."""
    from uuid import uuid4

    meds = [MagicMock(id=uuid4(), medicine_name="데모라니티딘정150밀리그램")]

    with patch("app.repositories.drug_recall_repository.DrugRecall.filter") as m:
      qs = MagicMock()
      qs.all = AsyncMock(return_value=[])
      m.return_value = qs
      await repo.find_recalls_for_medications(meds)

    kwargs = m.call_args.kwargs
    assert kwargs.get("is_non_drug") is False
    assert kwargs.get("is_hospital_only") is False
