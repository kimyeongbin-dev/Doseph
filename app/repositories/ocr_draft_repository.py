"""OcrDraft repository — 처방전 OCR 임시 저장소 CRUD.

본 레포지토리는 service 레이어가 호출하는 얇은 래퍼다. dedup·생명주기 정책
(24h, consumed_at) 은 서비스 레이어가 결정하고, 본 레포는 단순 SQL 조작만
수행한다.
"""

from datetime import datetime, timedelta
from uuid import UUID

from app.core.config import config
from app.models.ocr_draft import OcrDraft, OcrDraftStatusValue


class OcrDraftRepository:
    """OcrDraft CRUD — service 레이어 전용 진입점."""

    async def create_pending(
        self,
        profile_id: UUID | str,
        image_hash: str,
        filename: str | None,
    ) -> OcrDraft:
        """status=pending 인 신규 draft 를 생성한다.

        Args:
            profile_id: 업로드한 프로필 ID.
            image_hash: SHA256(image_bytes).
            filename: 원본 파일명 (없으면 None).

        Returns:
            저장된 OcrDraft (id 포함).
        """
        return await OcrDraft.create(
            profile_id=str(profile_id),
            image_hash=image_hash,
            filename=filename,
            status=OcrDraftStatusValue.PENDING.value,
        )

    async def find_active_by_hash(
        self,
        profile_id: UUID | str,
        image_hash: str,
    ) -> OcrDraft | None:
        """동일 프로필 + 동일 image_hash + 미consume draft 가 있으면 반환 (dedup).

        Args:
            profile_id: 사용자 프로필 ID.
            image_hash: SHA256(image_bytes).

        Returns:
            활성 draft 또는 None.
        """
        return await OcrDraft.filter(
            profile_id=str(profile_id),
            image_hash=image_hash,
            consumed_at__isnull=True,
        ).first()

    async def get_by_id(
        self,
        draft_id: UUID | str,
        profile_id: UUID | str,
    ) -> OcrDraft | None:
        """draft_id + profile_id 일치 시 반환 — 다른 사용자 draft 차단.

        Args:
            draft_id: 조회할 draft ID.
            profile_id: 요청자 프로필 ID (ownership 검증).

        Returns:
            본인 소유 draft 또는 None.
        """
        return await OcrDraft.filter(
            id=str(draft_id),
            profile_id=str(profile_id),
        ).first()

    async def list_active(self, profile_id: UUID | str) -> list[OcrDraft]:
        """현재 사용자의 활성 draft (24h 안 + 미consume) 리스트.

        UI 의 main 페이지 카드용. 최신순 정렬.

        Args:
            profile_id: 요청자 프로필 ID.

        Returns:
            활성 OcrDraft 리스트 (최신 순).
        """
        cutoff = datetime.now(tz=config.TIMEZONE) - timedelta(hours=24)
        return (
            await OcrDraft
            .filter(
                profile_id=str(profile_id),
                consumed_at__isnull=True,
                created_at__gte=cutoff,
            )
            .order_by("-created_at")
            .all()
        )

    async def update_result(
        self,
        draft_id: UUID | str,
        status: OcrDraftStatusValue,
        medicines: list[dict],
    ) -> None:
        """ai-worker 가 처리 완료 후 호출 — 결과를 저장한다.

        Args:
            draft_id: 처리한 draft ID.
            status: 결과 상태 (ready / no_text / no_candidates / failed).
            medicines: ExtractedMedicine 직렬화 리스트 (ready 일 때만 비어있지 않음).
        """
        await OcrDraft.filter(id=str(draft_id)).update(
            status=status.value,
            medicines=medicines,
            processed_at=datetime.now(tz=config.TIMEZONE),
        )

    async def mark_terminal_failure(
        self,
        draft_id: UUID | str,
        status: OcrDraftStatusValue,
    ) -> None:
        """ai-worker terminal failure 자동 롤백 — status + consumed_at 동시 set.

        ``no_text`` / ``no_candidates`` / ``failed`` 도달 시 ai-worker 가 그
        자리에서 호출한다. ``consumed_at`` 을 함께 채우므로 ``list_active`` 의
        ``consumed_at IS NULL`` 게이트로 자동 제외되고, ``find_active_by_hash``
        의 dedup 매칭에서도 자동 제외 → 동일 사진 재시도 시 새 draft 정상 생성.

        Args:
            draft_id: 처리 중이던 draft ID.
            status: terminal failure status (no_text / no_candidates / failed).
        """
        now = datetime.now(tz=config.TIMEZONE)
        await OcrDraft.filter(id=str(draft_id)).update(
            status=status.value,
            medicines=[],
            processed_at=now,
            consumed_at=now,
        )

    async def mark_consumed(self, draft_id: UUID | str, profile_id: UUID | str) -> bool:
        """Confirm 시 atomic 게이트 — consumed_at 을 1회만 설정.

        Args:
            draft_id: confirm 대상 draft ID.
            profile_id: 요청자 프로필 ID (ownership 검증).

        Returns:
            ``True`` 면 새로 consume 처리, ``False`` 면 이미 처리됨/없음/타인 소유.
        """
        affected = await OcrDraft.filter(
            id=str(draft_id),
            profile_id=str(profile_id),
            consumed_at__isnull=True,
        ).update(consumed_at=datetime.now(tz=config.TIMEZONE))
        return affected > 0

    async def delete_stale(self, max_age_hours: int = 24) -> int:
        """24h 이상 경과한 draft row 를 hard delete (cron 전용).

        consume 여부와 무관하게 ``created_at`` 기준 cutoff 를 넘긴 row 를 모두
        제거한다 — list_active 가 이미 동일 cutoff 로 검색 대상에서 빼고 있고,
        consumed 된 row 의 감사 보존도 24h 면 충분하다고 합의됨.

        Args:
            max_age_hours: cutoff 기준 시간 (기본 24h).

        Returns:
            삭제된 row 수.
        """
        cutoff = datetime.now(tz=config.TIMEZONE) - timedelta(hours=max_age_hours)
        return await OcrDraft.filter(created_at__lt=cutoff).delete()

    async def bulk_delete_by_profile(self, profile_id: UUID) -> int:
        """프로필의 모든 OCR draft 일괄 hard-delete.

        Profile cascade 삭제 흐름의 일부로 호출된다.

        Args:
            profile_id: 대상 프로필 UUID.

        Returns:
            삭제된 row 수.
        """
        return await OcrDraft.filter(profile_id=str(profile_id)).delete()
