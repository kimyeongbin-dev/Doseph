"""Medicine info repository module.

This module provides data access layer for the medicine_info table,
handling drug information queries, trigram fuzzy search (pg_trgm),
and bulk upsert operations for public API data synchronization.
"""

from datetime import UTC, datetime
import logging

from tortoise import Tortoise

from app.models.data_sync_log import DataSyncLog
from app.models.medicine_info import MedicineInfo

logger = logging.getLogger(__name__)


class MedicineInfoRepository:
  """Medicine info database repository for drug data management."""

  # ── 단건 조회 (ID / 품목코드 / 약품명) ───────────────────────────

  async def get_by_id(self, medicine_id: int) -> MedicineInfo | None:
    """Get medicine info by ID.

    Args:
        medicine_id: Medicine info primary key.

    Returns:
        MedicineInfo if found, None otherwise.
    """
    return await MedicineInfo.filter(id=medicine_id).first()

  async def get_by_item_seq(self, item_seq: str) -> MedicineInfo | None:
    """Get medicine info by public API item sequence code.

    Args:
        item_seq: Drug product code from public API.

    Returns:
        MedicineInfo if found, None otherwise.
    """
    return await MedicineInfo.filter(item_seq=item_seq).first()

  async def get_by_name(self, medicine_name: str) -> MedicineInfo | None:
    """Get medicine info by exact name match.

    Args:
        medicine_name: Drug product name in Korean.

    Returns:
        MedicineInfo if found, None otherwise.
    """
    return await MedicineInfo.filter(medicine_name=medicine_name).first()

  # ── 검색 (약품명 부분 일치) ─────────────────────────────────────

  async def search_by_name(
    self,
    query: str,
    limit: int = 10,
  ) -> list[MedicineInfo]:
    """Search medicine info by partial name match.

    Args:
        query: Search keyword for drug name.
        limit: Maximum number of results.

    Returns:
        List of matching MedicineInfo records.
    """
    return (
      await MedicineInfo
      .filter(
        medicine_name__icontains=query,
      )
      .limit(limit)
      .all()
    )

  # ── 유사도 검색 (pg_trgm 기반, OCR 오타 보정용) ────────────────
  # "다이레놀정" -> "타이레놀정" 처럼 글자가 비슷한 약품명을 찾아줌
  # pgvector(의미 유사도)와 별개로, 문자 수준 오타 교정 전용

  async def fuzzy_search_by_name(
    self,
    query: str,
    threshold: float = 0.3,
    limit: int = 3,
  ) -> list[dict]:
    """Search medicine by name using trigram similarity (pg_trgm).

    Handles OCR typos by comparing character-level similarity.
    For example, '다이레놀정' matches '타이레놀정' with high score.

    Args:
        query: OCR-extracted medicine name candidate (may contain typos).
        threshold: Minimum similarity score (0.0~1.0, default 0.3).
        limit: Maximum number of results to return.

    Returns:
        List of dicts with 'id', 'medicine_name', 'category', 'score'.
    """
    conn = Tortoise.get_connection("default")
    _, rows = await conn.execute_query(
      "SELECT id, medicine_name, category, "
      "similarity(medicine_name, $1) AS score "
      "FROM medicine_info "
      "WHERE similarity(medicine_name, $1) > $2 "
      "ORDER BY score DESC "
      "LIMIT $3",
      [query, threshold, limit],
    )
    return [
      {
        "id": row["id"],
        "medicine_name": row["medicine_name"],
        "category": row["category"],
        "score": float(row["score"]),
      }
      for row in rows
    ]

  # ── 자동완성용 검색 (2-단계 fast path) ───────────────────────────
  # 흐름: 1단계 prefix only -> limit 미달 시 2단계 trigram fallback -> 합쳐 반환
  # 핵심: 대부분의 자동완성 typing 케이스는 prefix 만으로 종결 (~1ms).
  #       오타 (예: "다이레놀") 는 trigram fallback 으로 보완 (~5-10ms).
  async def autocomplete_by_name(
    self,
    query: str,
    limit: int = 8,
    threshold: float = 0.2,
  ) -> list[dict]:
    """약품명 자동완성 — prefix 1순위, trigram fallback 2순위 (2-단계 fast path).

    OCR 결과 인라인 편집 / "+ 약 추가" 모달의 실시간 자동완성. 단일 OR 쿼리로
    합치는 대신 2-단계로 나눠 일반 typing 케이스 (prefix 일치) 의 비용을 최소화.

    성능 가이드:
      - 1단계 (prefix): ``medicine_name ILIKE q || '%'`` — GIN trgm 인덱스 활용,
        308K rows 에서 ~1ms.
      - 2단계 (trigram): 1단계 결과가 ``limit`` 미만일 때만 실행. ``medicine_name % q``
        연산자 (default ``pg_trgm.similarity_threshold`` 0.3 보다 완화된 0.2 적용)
        로 인덱스 적중. ~5-10ms.

    Args:
        query: 사용자 입력 (공백 trim 가정, 호출 측에서 정규화).
        limit: 최대 결과 수 (default 8 — dropdown 1 화면 수용).
        threshold: trigram similarity 최소값 (자동완성용 완화 default 0.2).

    Returns:
        list[dict]: ``[{id, medicine_name, score}, ...]`` — prefix 결과(score=1.0)
            먼저, trigram 결과(score<1.0) 가 score desc + name asc 로 뒤따른다.
    """
    conn = Tortoise.get_connection("default")

    # ── 1단계: prefix only — 자동완성 hot path ──
    # SELECT 절에 similarity 함수 호출이 없어 LIMIT 전까지 비용 최소화.
    # score 1.0 은 placeholder (prefix 일치는 항상 trigram 보다 우선).
    _, prefix_rows = await conn.execute_query(
      "SELECT id, medicine_name "
      "FROM medicine_info "
      "WHERE medicine_name ILIKE $1 || '%' "
      "ORDER BY medicine_name ASC "
      "LIMIT $2",
      [query, limit],
    )
    results = [{"id": row["id"], "medicine_name": row["medicine_name"], "score": 1.0} for row in prefix_rows]
    if len(results) >= limit:
      return results

    # ── 2단계: trigram fallback — prefix 부족 시에만 ──
    # `%` 연산자가 인덱스를 가장 잘 탄다. similarity 함수는 SELECT 절에서만
    # 호출하여 ORDER BY 정렬 비용을 최소화. 1단계 hit 한 id 는 NOT IN 으로 중복 제거.
    remaining = limit - len(results)
    prefix_ids = [row["id"] for row in prefix_rows]
    if prefix_ids:
      _, trigram_rows = await conn.execute_query(
        "SELECT id, medicine_name, similarity(medicine_name, $1) AS score "
        "FROM medicine_info "
        "WHERE medicine_name % $1 "
        "  AND similarity(medicine_name, $1) >= $2 "
        "  AND id <> ALL($3::int[]) "
        "ORDER BY score DESC, medicine_name ASC "
        "LIMIT $4",
        [query, threshold, prefix_ids, remaining],
      )
    else:
      _, trigram_rows = await conn.execute_query(
        "SELECT id, medicine_name, similarity(medicine_name, $1) AS score "
        "FROM medicine_info "
        "WHERE medicine_name % $1 "
        "  AND similarity(medicine_name, $1) >= $2 "
        "ORDER BY score DESC, medicine_name ASC "
        "LIMIT $3",
        [query, threshold, remaining],
      )
    results.extend(
      {
        "id": row["id"],
        "medicine_name": row["medicine_name"],
        "score": float(row["score"]),
      }
      for row in trigram_rows
    )
    return results

  async def ensure_pg_trgm(self) -> None:
    """Ensure pg_trgm extension is available in the database.

    Creates the extension if it does not already exist.
    Required for fuzzy_search_by_name to work.
    """
    conn = Tortoise.get_connection("default")
    await conn.execute_query("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    logger.info("pg_trgm extension verified")

  # ── UPSERT (item_seq 기준으로 신규 삽입 또는 기존 갱신) ─────────

  async def upsert_from_api(self, item_data: dict) -> tuple[MedicineInfo, bool]:
    """Insert or update a single medicine info record from API data.

    Uses item_seq as the unique key for upsert operations.

    Args:
        item_data: Transformed API data dictionary with model field names.

    Returns:
        Tuple of (MedicineInfo instance, created flag).
    """
    item_seq = item_data.pop("item_seq")
    item_data["last_synced_at"] = datetime.now(tz=UTC)

    instance, created = await MedicineInfo.update_or_create(
      defaults=item_data,
      item_seq=item_seq,
    )
    return instance, created

  # ── 대량 UPSERT (API 수집 데이터를 배치로 처리) ────────────────
  # 흐름: items 순회 -> upsert_from_api 호출 -> 성공/실패 카운트
  #       -> batch_size 마다 진행률 로그 출력

  async def bulk_upsert(
    self,
    items: list[dict],
    batch_size: int = 100,
  ) -> dict[str, int]:
    """Bulk upsert medicine info records from API data.

    Processes items in batches using update_or_create for each item.

    Args:
        items: List of transformed API data dictionaries.
        batch_size: Number of items to process before logging progress.

    Returns:
        Dictionary with 'inserted' and 'updated' counts.
    """
    inserted = 0
    updated = 0
    total = len(items)

    for idx, item_data in enumerate(items, start=1):
      try:
        _, created = await self.upsert_from_api(item_data.copy())
        if created:
          inserted += 1
        else:
          updated += 1
      except Exception:
        logger.exception(
          "Failed to upsert item_seq=%s",
          item_data.get("item_seq", "unknown"),
        )
        continue

      if idx % batch_size == 0:
        logger.info(
          "Upsert progress: %d/%d (inserted=%d, updated=%d)",
          idx,
          total,
          inserted,
          updated,
        )

    logger.info(
      "Bulk upsert complete: total=%d, inserted=%d, updated=%d",
      total,
      inserted,
      updated,
    )
    return {"inserted": inserted, "updated": updated}

  # ── 동기화 이력 조회 (증분 업데이트 시작 날짜 결정용) ────────────

  async def get_last_sync_date(self) -> str | None:
    """Get the last successful sync date for medicine_info.

    Returns:
        Date string in YYYYMMDD format, or None if no sync recorded.
    """
    last_log = (
      await DataSyncLog
      .filter(
        sync_type="medicine_info",
        status="SUCCESS",
      )
      .order_by("-sync_date")
      .first()
    )

    if not last_log:
      return None
    return last_log.sync_date.strftime("%Y%m%d")

  # ── 통계 ─────────────────────────────────────────────────────────

  async def count_all(self) -> int:
    """Count total medicine info records.

    Returns:
        Total number of records in medicine_info table.
    """
    return await MedicineInfo.all().count()
