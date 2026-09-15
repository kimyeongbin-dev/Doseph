"""Medication service module.

This module provides business logic for medication management operations
including creation, updates, and ownership verification.
"""

from dataclasses import dataclass
import logging
from uuid import UUID

from fastapi import HTTPException, status
from tortoise.transactions import in_transaction

from app.dtos.drug_info import DrugInfoResponse, DrugInteraction, PrecautionSection
from app.dtos.medication import MedicationBulkDeleteResponse, MedicationCreate, MedicationUpdate, PrescriptionDateItem
from app.dtos.recall import RecallAlertDTO, RecallStatusDTO
from app.models.medication import Medication
from app.models.prescription_group import PrescriptionGroupSource
from app.repositories.drug_recall_repository import DrugRecallRepository
from app.repositories.medication_repository import MedicationRepository
from app.repositories.medicine_info_repository import MedicineInfoRepository
from app.repositories.prescription_group_repository import PrescriptionGroupRepository
from app.repositories.profile_repository import ProfileRepository
from app.services.lifestyle_guide_service import LifestyleGuideService
from app.services.recall_alert_builder import build_alert, build_status
from app.services.recall_notification_service import check_and_alert_on_medication_save

logger = logging.getLogger(__name__)


# ── 마이페이지 batch 응답 wrapper (§A.6.1) ────────────────────────────
# medication 모델 자체엔 recall_status 컬럼이 없고 응답 시점에만 필요한
# 메타 정보라 dataclass 로 묶어 전달한다. router 가 unpack 후 응답 스키마
# 에 반영.


@dataclass
class MedicationWithRecallStatus:
    """Service-level pair of (medication row, recall_status payload)."""

    medication: Medication
    recall_status: RecallStatusDTO | None


class MedicationService:
    """Medication business logic service for prescription management."""

    def __init__(self) -> None:
        self.repository = MedicationRepository()
        self.profile_repository = ProfileRepository()
        self.lifestyle_guide_service = LifestyleGuideService()
        self.prescription_group_repository = PrescriptionGroupRepository()

    async def _verify_profile_ownership(self, profile_id: UUID, account_id: UUID) -> None:
        """Verify profile ownership.

        Args:
            profile_id: Profile UUID to verify.
            account_id: Account UUID that should own the profile.

        Raises:
            HTTPException: If profile not found or access denied.
        """
        profile = await self.profile_repository.get_by_id(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found.",
            )
        if profile.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this profile.",
            )

    async def _verify_medication_ownership(self, medication: Medication, account_id: UUID) -> None:
        """Verify medication ownership through profile.

        Args:
            medication: Medication to verify ownership for.
            account_id: Account UUID that should own the medication.

        Raises:
            HTTPException: If access denied to medication.
        """
        await medication.fetch_related("profile")
        if medication.profile.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this medication.",
            )

    async def get_medication(self, medication_id: UUID) -> Medication:
        """Get medication by ID.

        Args:
            medication_id: Medication UUID.

        Returns:
            Medication: Medication object.

        Raises:
            HTTPException: If medication not found.
        """
        medication = await self.repository.get_by_id(medication_id)
        if not medication:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medication not found.",
            )
        return medication

    async def get_medications_by_profile(self, profile_id: UUID) -> list[Medication]:
        """Get all medications for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[Medication]: List of medications.
        """
        return await self.repository.get_all_by_profile(profile_id)

    async def get_medications_by_profile_with_owner_check(self, profile_id: UUID, account_id: UUID) -> list[Medication]:
        """Get all medications for a profile with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.

        Returns:
            list[Medication]: List of medications if profile is owned by account.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.repository.get_all_by_profile(profile_id)

    # ── §A.2.2: 마이페이지 batch lookup (recall_status 첨부) ────────────
    # 흐름: 소유 확인 -> medication 리스트 조회
    #       -> drug_recall_repo.find_recalls_for_medications (단일 쿼리)
    #       -> medication 마다 build_status 로 라벨 페이로드 생성
    # N+1 회피: repository 쿼리 1회 + 메모리 그룹핑.

    async def list_medications_with_recall_status_with_owner_check(
        self,
        profile_id: UUID,
        account_id: UUID,
    ) -> list[MedicationWithRecallStatus]:
        """List a profile's medications, each paired with its recall_status.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.

        Returns:
            list[MedicationWithRecallStatus]: One entry per medication row.
                ``recall_status`` is ``None`` when no recall matches.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        medications = await self.repository.get_all_by_profile(profile_id)
        if not medications:
            return []

        drug_recall_repo = DrugRecallRepository()
        grouping = await drug_recall_repo.find_recalls_for_medications(medications)
        return [
            MedicationWithRecallStatus(
                medication=med,
                recall_status=build_status(grouping.get(med.id, [])),
            )
            for med in medications
        ]

    async def _build_recall_alert_for(self, medication: Medication) -> RecallAlertDTO | None:
        """등록 시점 모달 페이로드 빌더 — find_by_item_seq_or_name → build_alert.

        Returns:
            ``RecallAlertDTO`` 또는 매칭 없을 시 ``None``.
        """
        drug_recall_repo = DrugRecallRepository()
        rows = await drug_recall_repo.find_by_item_seq_or_name(
            item_seq=getattr(medication, "item_seq", None),
            product_name=getattr(medication, "medicine_name", None),
        )
        return build_alert(rows)

    async def get_active_medications(self, profile_id: UUID) -> list[Medication]:
        """Get active medications for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[Medication]: List of active medications.
        """
        return await self.repository.get_active_by_profile(profile_id)

    async def get_active_medications_with_owner_check(self, profile_id: UUID, account_id: UUID) -> list[Medication]:
        """Get active medications for a profile with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.

        Returns:
            list[Medication]: List of active medications if profile is owned by account.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.repository.get_active_by_profile(profile_id)

    async def get_inactive_medications_with_owner_check(self, profile_id: UUID, account_id: UUID) -> list[Medication]:
        """Get completed or expired medications for a profile with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.

        Returns:
            list[Medication]: List of inactive medications if profile is owned by account.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.repository.get_inactive_by_profile(profile_id)

    async def get_prescription_dates_with_owner_check(
        self,
        profile_id: UUID,
        account_id: UUID,
    ) -> list[PrescriptionDateItem]:
        """Get prescription date summary for a profile with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.

        Returns:
            list[PrescriptionDateItem]: Grouped prescription dates sorted by date descending.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.repository.get_prescription_dates_by_profile(profile_id)

    async def get_medications_by_account(self, account_id: UUID) -> list[Medication]:
        """Get medications for all profiles of an account.

        Args:
            account_id: Account UUID.

        Returns:
            list[Medication]: List of medications for all account profiles.
        """
        profiles = await self.profile_repository.get_all_by_account(account_id)
        profile_ids = [p.id for p in profiles]
        return await self.repository.get_all_by_profiles(profile_ids)

    async def get_medication_with_owner_check(self, medication_id: UUID, account_id: UUID) -> Medication:
        """Get medication with ownership verification.

        Args:
            medication_id: Medication UUID.
            account_id: Account UUID for ownership check.

        Returns:
            Medication: Medication if owned by account.
        """
        medication = await self.get_medication(medication_id)
        await self._verify_medication_ownership(medication, account_id)
        return medication

    async def create_medication(
        self,
        profile_id: UUID,
        data: MedicationCreate,
    ) -> Medication:
        """Create new medication — 단건 호출 = 단건 처방전 그룹 자동 생성.

        OCR 흐름과 마찬가지로 한 호출 = 한 처방전 도메인 의미를 유지하기 위해
        manual 등록도 새 ``PrescriptionGroup`` 을 만들고 그 FK 를 채운다. 사용자가
        같은 처방전에 여러 약을 추가하려면 future bulk endpoint 가 필요하다.

        Args:
            profile_id: Profile UUID.
            data: Medication creation data.

        Returns:
            Medication: Created medication.
        """
        async with in_transaction():
            group = await self.prescription_group_repository.create(
                profile_id=profile_id,
                dispensed_date=data.dispensed_date,
                department=None,
                source=PrescriptionGroupSource.MANUAL,
            )
            medication = await self.repository.create(
                profile_id=profile_id,
                prescription_group_id=group.id,
                medicine_name=data.medicine_name,
                dose_per_intake=data.dose_per_intake,
                intake_instruction=data.intake_instruction,
                intake_times=data.intake_times,
                total_intake_count=data.total_intake_count,
                remaining_intake_count=data.remaining_intake_count or data.total_intake_count,
                start_date=data.start_date,
                end_date=data.end_date,
                dispensed_date=data.dispensed_date,
                expiration_date=data.expiration_date,
            )

        # ── F3: 즉시 회수 체크 (Phase 7, PLAN §16.3.2 헬퍼 위임) ────────
        # 등록 시점에 이미 회수 발표된 약이면 cron 24h 대기 없이 즉시 알림.
        # 알림 dispatch 실패는 medication 등록을 망치지 않도록 격리.
        try:
            await check_and_alert_on_medication_save(medication)
        except Exception:
            logger.exception("[F3] recall hook failed for medication=%s", getattr(medication, "id", "?"))

        # ── §A.2.1: 등록 직후 회수 모달 페이로드 첨부 ──────────────────
        # 흐름: drug_recall_repo.find_by_item_seq_or_name -> build_alert
        #       -> medication 객체에 recall_alert 속성 attach
        # MedicationResponse 의 from_attributes=True 가 자동 매핑한다.
        # ORM 미초기화 같은 환경 문제로 매칭이 실패해도 medication 등록
        # 자체는 망치지 않도록 격리한다 (recall_alert=None 으로 fallback).
        try:
            medication.recall_alert = await self._build_recall_alert_for(medication)
        except Exception:
            logger.exception(
                "[recall] alert builder failed for medication=%s",
                getattr(medication, "id", "?"),
            )
            medication.recall_alert = None

        return medication

    async def create_medication_with_owner_check(
        self,
        profile_id: UUID,
        account_id: UUID,
        data: MedicationCreate,
    ) -> Medication:
        """Create medication with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.
            data: Medication creation data.

        Returns:
            Medication: Created medication if profile is owned by account.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.create_medication(profile_id, data)

    async def update_medication(
        self,
        medication_id: UUID,
        data: MedicationUpdate,
    ) -> Medication:
        """Update medication.

        Args:
            medication_id: Medication UUID.
            data: Medication update data.

        Returns:
            Medication: Updated medication.
        """
        medication = await self.get_medication(medication_id)
        update_data = data.model_dump(exclude_unset=True)
        return await self.repository.update(medication, **update_data)

    async def update_medication_with_owner_check(
        self,
        medication_id: UUID,
        account_id: UUID,
        data: MedicationUpdate,
    ) -> Medication:
        """Update medication with ownership verification.

        Args:
            medication_id: Medication UUID.
            account_id: Account UUID for ownership check.
            data: Medication update data.

        Returns:
            Medication: Updated medication if owned by account.
        """
        medication = await self.get_medication_with_owner_check(medication_id, account_id)
        update_data = data.model_dump(exclude_unset=True)
        return await self.repository.update(medication, **update_data)

    async def decrement_and_deactivate_if_exhausted(self, medication: Medication) -> Medication:
        """Decrement remaining intake count and deactivate medication if exhausted.

        복용 완료 시 잔여 횟수를 1 감소시키고, 0이 되면 is_active=False로 자동 비활성화합니다.
        처방전 만료와는 별개로, 복용 횟수 소진 기준의 자동 종료 로직입니다.

        Args:
            medication: Medication to update.

        Returns:
            Medication: Updated medication. Deactivated if remaining count reaches zero.
        """
        medication = await self.repository.decrement_remaining_count(medication)
        # 잔여 횟수 0 도달 시 해당 처방전 비활성화 (더 이상 복용 기록 생성 안 됨)
        if medication.remaining_intake_count == 0:
            medication = await self.repository.update(medication, is_active=False)
        return medication

    async def deactivate_medication(self, medication_id: UUID) -> Medication:
        """Deactivate medication (stop taking).

        Args:
            medication_id: Medication UUID.

        Returns:
            Medication: Deactivated medication.
        """
        medication = await self.get_medication(medication_id)
        return await self.repository.update(medication, is_active=False)

    async def delete_medication(self, medication_id: UUID) -> None:
        """Delete medication (soft delete).

        Args:
            medication_id: Medication UUID to delete.
        """
        medication = await self.get_medication(medication_id)
        await self.repository.soft_delete(medication)

    async def delete_medication_with_owner_check(self, medication_id: UUID, account_id: UUID) -> None:
        """Delete medication with ownership verification (soft delete).

        Args:
            medication_id: Medication UUID to delete.
            account_id: Account UUID for ownership check.
        """
        medication = await self.get_medication_with_owner_check(medication_id, account_id)
        await self.repository.soft_delete(medication)

    # ── Bulk soft delete (계정 소유 medication 다건 동시 삭제) ────────────
    # 흐름: 계정의 프로필 목록 조회 -> bulk_soft_delete (단일 UPDATE)
    #       -> 응답에 deleted_count + 누락 ids 보고
    async def bulk_delete_with_owner_check(
        self,
        ids: list[UUID],
        account_id: UUID,
    ) -> MedicationBulkDeleteResponse:
        """다건 medication soft delete — ownership 위반 ids 는 silently skip.

        Args:
            ids: 삭제 요청된 medication ID 목록 (1~100건, DTO 에서 강제).
            account_id: 요청자 계정 ID — 본인 프로필 소유 medications 만 처리.

        Returns:
            ``MedicationBulkDeleteResponse`` — 처리된 개수 + 건너뛴 ids.
        """
        profiles = await self.profile_repository.get_all_by_account(account_id)
        profile_ids = [p.id for p in profiles]
        deletable_ids = await self.repository.find_deletable_ids(ids, profile_ids)
        deleted_count = await self.repository.bulk_soft_delete(ids, profile_ids)
        skipped = await self._collect_skipped_ids(ids, deletable_ids) if deleted_count < len(ids) else []
        return MedicationBulkDeleteResponse(deleted_count=deleted_count, skipped_ids=skipped)

    # ── 처방전 그룹 단위 삭제 (cascade — 가이드 + 챌린지) ──────────────
    # 흐름: medication 그룹 soft -> 그 프로필의 active lifestyle_guide cascade
    #       (가이드 cascade 안에서 챌린지 정책 — 미시작 soft, 활성 보존 — 적용)
    # 단건 삭제는 ``bulk_delete_with_owner_check`` 그대로 (cascade 없음).

    async def delete_prescription_group_with_owner_check(
        self,
        ids: list[UUID],
        profile_id: UUID,
        account_id: UUID,
    ) -> MedicationBulkDeleteResponse:
        """처방전 그룹 삭제 — medication 그룹 + 그 프로필의 가이드/챌린지 cascade.

        Args:
            ids: 처방전 그룹에 속한 medication ID 목록 (1~100건).
            profile_id: 그룹 소유 프로필 — owner check + 가이드 cascade scope.
            account_id: 요청 계정 — 프로필이 이 계정 소속인지 검증.

        Returns:
            ``MedicationBulkDeleteResponse`` — 삭제된 medication 수 + 건너뛴 ids.

        Raises:
            HTTPException: 404/403 if profile not found / not owned.
        """
        await self._verify_profile_ownership(profile_id, account_id)

        async with in_transaction():
            deletable_ids = await self.repository.find_deletable_ids(ids, [profile_id])
            deleted_count = await self.repository.bulk_soft_delete(ids, [profile_id])
            skipped = await self._collect_skipped_ids(ids, deletable_ids) if deleted_count < len(ids) else []
            await self.lifestyle_guide_service.cascade_delete_active_guides_by_profile(profile_id)

        return MedicationBulkDeleteResponse(deleted_count=deleted_count, skipped_ids=skipped)

    async def _collect_skipped_ids(
        self,
        requested_ids: list[UUID],
        deletable_ids: list[UUID],
    ) -> list[UUID]:
        """요청된 ids 중 실제로 지우지 못한 것을 고른다.

        ⚠️ hard delete 로 바뀌면서 계산 시점이 **삭제 전**으로 옮겨졌다(QA-01).
        전에는 삭제 후 ``deleted_at IS NOT NULL`` 로 "방금 지운 것"을 되짚었는데,
        행이 물리적으로 사라지면 **사후에 알아낼 방법이 없다.**

        Args:
            requested_ids: 사용자가 삭제를 요청한 ID 목록.
            deletable_ids: 삭제 직전에 확정한 "존재 + 본인 소유" ID 목록.

        Returns:
            소유가 아니거나 이미 없어서 건너뛴 ID 목록.
        """
        deletable = set(deletable_ids)
        return [rid for rid in requested_ids if rid not in deletable]

    async def get_drug_info_with_owner_check(self, medication_id: UUID, account_id: UUID) -> DrugInfoResponse:
        """Get drug information from MedicineInfo DB with ownership verification.

        ``warnings`` 와 ``side_effects`` 는 식약처 마스터 DB (``MedicineInfo`` 테이블)
        의 ``precautions`` / ``side_effects`` TEXT 컬럼에서 줄바꿈 분할로 list 화 한다.
        ``interactions`` 는 컬럼이 없으므로 항상 빈 배열 — 향후 별도 마스터 도입 시 채움.

        Args:
            medication_id: Medication UUID.
            account_id: Account UUID for ownership check.

        Returns:
            DrugInfoResponse: 매칭된 마스터 데이터 또는 빈 배열 (DB miss / NULL).
        """
        medication = await self.get_medication_with_owner_check(medication_id, account_id)
        return await self._get_drug_info(medication.medicine_name)

    async def _get_drug_info(self, medicine_name: str) -> DrugInfoResponse:
        """MedicineInfo + medicine_chunk 에서 약품 정보 조회 — LLM 호출 없음.

        흐름:
          1) 정확 일치 (``get_by_name``) → 미일치 시 ILIKE fallback
          2) MedicineInfo 의 precautions/side_effects/dosage 추출
          3) medicine_chunk 의 ``section='drug_interaction'`` chunks 를
             DrugInteraction list 로 변환 (각 chunk = 1 DrugInteraction)

        Args:
            medicine_name: 매칭할 약품명.

        Returns:
            DrugInfoResponse — DB hit 시 채워진 값, miss / NULL 시 빈 배열.
        """
        repo = MedicineInfoRepository()
        info = await repo.get_by_name(medicine_name)
        if info is None:
            candidates = await repo.search_by_name(medicine_name, limit=1)
            info = candidates[0] if candidates else None

        if info is None:
            return DrugInfoResponse(medicine_name=medicine_name)

        interactions = await _load_drug_interactions(info.id)

        return DrugInfoResponse(
            medicine_name=info.medicine_name,
            warnings=_to_precaution_sections(info.precautions),
            side_effects=info.side_effects or [],
            dosage=info.dosage or "",
            interactions=interactions,
        )


def _to_precaution_sections(precautions: dict | None) -> list[PrecautionSection]:
    """JSONB precautions dict → list[PrecautionSection] (카테고리 순서 보존).

    None / 빈 dict / 비-dict 입력 → 빈 list.
    """
    if not precautions or not isinstance(precautions, dict):
        return []
    return [PrecautionSection(category=cat, items=list(items or [])) for cat, items in precautions.items() if items]


# ── medicine_chunk drug_interaction → DrugInteraction list ─────────
# 흐름: medicine_info_id 매칭 + section='drug_interaction' chunks 조회 (chunk_index 순)
#       -> 각 chunk 의 content 헤더 ([약: ...] [성분: ...] [약물 상호작용]) 제거
#       -> 첫 줄 (또는 첫 번호 list) 을 drug 라벨, 나머지를 description 으로
async def _load_drug_interactions(medicine_info_id: int) -> list[DrugInteraction]:
    """medicine_chunk 의 drug_interaction section chunks 를 DrugInteraction list 로.

    Args:
        medicine_info_id: 부모 medicine_info.id.

    Returns:
        list[DrugInteraction] - chunk_index 오름차순. chunk 0건이면 빈 list.
    """
    from app.models.medicine_chunk import MedicineChunk, MedicineChunkSection

    chunks = (
        await MedicineChunk
        .filter(
            medicine_info_id=medicine_info_id,
            section=MedicineChunkSection.DRUG_INTERACTION.value,
        )
        .order_by("chunk_index")
        .all()
    )
    return [DrugInteraction(**_chunk_to_interaction(c.content, c.chunk_index)) for c in chunks if c.content]


def _chunk_to_interaction(content: str, chunk_index: int) -> dict[str, str]:
    r"""Chunk content 헤더 제거 + drug/description 분리.

    헤더 패턴: ``[약: name] [성분: ...] [약물 상호작용]\n<제목>\n<본문>``
    헤더가 있는 첫 줄 ``[`` 시작은 모두 제거, 그 다음 첫 비공백 줄을 drug 라벨,
    나머지를 description 으로. 헤더가 없으면 chunk_index 기반 라벨.
    """
    raw_lines = [line for line in (content or "").split("\n") if line.strip()]
    body_lines = [
        line for line in raw_lines if not line.lstrip().startswith("[약:") and not line.lstrip().startswith("[성분:")
    ]
    if not body_lines:
        return {"drug": f"상호작용 #{chunk_index + 1}", "description": content.strip()[:500]}
    drug_label = body_lines[0].strip()
    description = "\n".join(body_lines[1:]).strip() or drug_label
    if len(drug_label) > 60:
        # 첫 줄이 너무 길면 chunk_index 라벨로 fallback (가독성)
        return {"drug": f"상호작용 #{chunk_index + 1}", "description": "\n".join(body_lines).strip()}
    return {"drug": drug_label, "description": description}
