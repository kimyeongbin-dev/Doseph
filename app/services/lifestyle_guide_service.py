"""Lifestyle guide service — RQ producer + SSE long-poll thin layer.

본 서비스는 더 이상 LLM 을 직접 호출하지 않는다. ``generate_guide`` 가
``lifestyle_guides`` 에 pending row 를 INSERT 하고 RQ ``ai`` 큐에
``ai_worker.domains.lifestyle.jobs.process_lifestyle_guide_task`` 를 enqueue
한 뒤 즉시 ``LifestyleGuide`` (status='pending') 를 반환한다. 이후
``stream_guide_states`` 가 SSE 로 status 변화를 push 한다.

ai-worker 가 ``content`` 를 채우고 status='ready' 로 UPDATE 하면 GET
``/lifestyle-guides/{id}`` 또는 SSE 가 곧바로 ready payload 를 응답한다.

Phase B (입력 fingerprint dedupe): 같은 (활성 약물 set + 프롬프트 버전) 의
ready 가이드가 이미 있으면 새 가이드를 생성하지 않고 그것을 그대로 반환.
"""

import asyncio
from collections.abc import AsyncIterator
import hashlib
import json
import logging
import os
import time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from rq import Queue

from app.core.redis_client import make_sync_redis
from app.dtos.lifestyle_guide import LifestyleGuideStatus
from app.models.challenge import Challenge
from app.models.lifestyle_guide import LifestyleGuide
from app.models.medication import Medication
from app.repositories.challenge_repository import ChallengeRepository
from app.repositories.lifestyle_guide_repository import LifestyleGuideRepository
from app.repositories.medication_repository import MedicationRepository
from app.repositories.prescription_group_repository import PrescriptionGroupRepository
from app.repositories.profile_repository import ProfileRepository

logger = logging.getLogger(__name__)

_GUIDE_JOB_REF = "ai_worker.domains.lifestyle.jobs.process_lifestyle_guide_task"

# 가이드 생성 시 LLM 으로 한 번에 받아 DB 에 저장하는 챌린지 총 개수.
# 사용자에겐 5개씩 점진 노출 — `revealed_challenge_count` 가 5 → 10 → 15 으로
# 증가. 매 "더 보기" 클릭은 단일 UPDATE 만 발생, LLM 호출 0회.
_TOTAL_CHALLENGES = 15
_REVEAL_STEP = 5

# SSE long-polling — nginx default proxy_read_timeout(60s) 안에 close
_STREAM_MAX_SECONDS = 50
_STREAM_TICK_SECONDS = 0.5

# 프롬프트 / 분배 규칙 / fingerprint 입력 변경 시 bump — 기존 ready 가이드의
# fingerprint 가 stale 처리되어 새 LLM 호출 강제된다.
# v2: 1일 챌린지 강제 + 일관성 instruction (Phase B 도입 시점)
# v3: 처방전 그룹 단위 + health_survey fingerprint 합산 + 챌린지 15개 한 번에 생성
#     (사용자 점진 노출 정책). 카테고리는 5개 유지 (symptom = 예상 증상/모니터링).
# v4: health_survey FE/BE key 이름 매핑 fix (is_smoking/is_drinking/conditions
#     등) — 기존 v3 가이드는 prompt 에 사용자 건강정보가 leak 되어 있었으므로
#     v4 로 강제 재생성 트리거.
_GUIDE_PROMPT_VERSION = "v4"


def _compute_input_fingerprint(snapshot: list[dict], health_survey: dict | None) -> str:
    """가이드 입력 fingerprint — 같은 (약물 set + 건강정보) 면 같은 가이드.

    Args:
        snapshot: medication snapshot dict list (해당 처방전 그룹의 active meds).
        health_survey: ``Profile.health_survey`` JSONField 의 dict 값 (또는 None).
            나이/성별/알레르기/운동/흡연/키/몸무게/기저질환 등 사용자가 입력한
            모든 키가 dedupe 키에 영향. 사용자가 설문 한 필드라도 수정하면
            fingerprint 가 달라져 새 가이드를 받을 수 있다.

    Returns:
        SHA-256 hex (64 chars).
    """
    names = sorted((m.get("medicine_name") or "") for m in snapshot)
    payload = json.dumps(
        {
            "prompt_ver": _GUIDE_PROMPT_VERSION,
            "medications": names,
            "health": health_survey or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _med_to_dict(med: Medication) -> dict:
    """Medication ORM -> snapshot-safe dict (LLM prompt + DB JSONField 공용).

    날짜 필드는 ISO 문자열로 저장해 FE 에서 처방일 라벨에 활용한다.
    LLM 프롬프트는 medicine_name/category/intake_instruction/dose_per_intake 만
    참조하므로 추가 필드는 prompt 출력에 영향 없음.
    """
    return {
        "medicine_name": med.medicine_name,
        "category": getattr(med, "category", None),
        "intake_instruction": getattr(med, "intake_instruction", None),
        "dose_per_intake": getattr(med, "dose_per_intake", None),
        "dispensed_date": med.dispensed_date.isoformat() if med.dispensed_date else None,
        "start_date": med.start_date.isoformat() if med.start_date else None,
        "end_date": med.end_date.isoformat() if med.end_date else None,
    }


class LifestyleGuideService:
    """RQ producer + SSE consumer 측 thin service."""

    def __init__(self) -> None:
        self.medication_repo = MedicationRepository()
        self.guide_repo = LifestyleGuideRepository()
        self.challenge_repo = ChallengeRepository()
        self.profile_repo = ProfileRepository()
        self.prescription_group_repo = PrescriptionGroupRepository()

        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379")
        self._queue = Queue("ai", connection=make_sync_redis(redis_url))

    # ── 가이드 생성 (RQ producer + 처방전 단위 + 건강정보 fingerprint dedupe) ──
    # 흐름: 처방전 그룹 검증 -> 그 group 의 active medications + Profile.health_survey
    #       -> fingerprint = sha256(약물 + 건강정보 + 프롬프트버전)
    #       -> 동일 fingerprint ready 가이드 존재 시 즉시 그것 반환 (LLM 호출 X)
    #       -> 없으면 pending row INSERT (prescription_group_id 채움) + RQ enqueue
    async def enqueue_guide_generation(
        self,
        profile_id: UUID,
        prescription_group_id: UUID,
    ) -> LifestyleGuide:
        """처방전 그룹 단위로 가이드 생성을 등록한다.

        같은 (그룹의 약물 set + Profile 건강정보) 면 같은 fingerprint → 기존
        ready 가이드 즉시 반환 (LLM 호출 X). 다르면 pending row 만들고 RQ enqueue.

        Args:
            profile_id: 가이드 소유 프로필.
            prescription_group_id: 가이드를 만들 처방전 그룹.

        Returns:
            ``LifestyleGuide``. 신규 enqueue 시 status='pending', dedupe hit
            시 status='ready'.

        Raises:
            HTTPException 404/403: 그룹 존재 X / 소유자 불일치.
            HTTPException 409 (NO_ACTIVE_MEDICATIONS): 그룹에 active 약 없음.
        """
        group = await self.prescription_group_repo.get_by_id(prescription_group_id)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription group not found.",
            )
        if str(group.profile_id) != str(profile_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this prescription group.",
            )

        meds = await self.medication_repo.get_active_by_prescription_group(prescription_group_id)
        if not meds:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "NO_ACTIVE_MEDICATIONS",
                    "message": "이 처방전엔 복용 중인 약이 없어 가이드를 만들 수 없어요.",
                    "redirect_to": "/medication",
                },
            )

        profile = await self.profile_repo.get_by_id(profile_id)
        health_survey = profile.health_survey if profile else None

        snapshot = [_med_to_dict(m) for m in meds]
        fingerprint = _compute_input_fingerprint(snapshot, health_survey)

        existing = await self.guide_repo.get_ready_by_fingerprint(profile_id, fingerprint)
        if existing is not None:
            logger.info(
                "[GUIDE] dedupe hit guide_id=%s profile_id=%s group_id=%s fingerprint=%s",
                existing.id,
                profile_id,
                prescription_group_id,
                fingerprint[:12],
            )
            return existing

        guide = await self.guide_repo.create_pending(
            profile_id=profile_id,
            medication_snapshot=snapshot,
            input_fingerprint=fingerprint,
            prescription_group_id=prescription_group_id,
        )
        self._queue.enqueue(_GUIDE_JOB_REF, str(guide.id), str(profile_id))
        logger.info(
            "[GUIDE] enqueued guide_id=%s profile_id=%s group_id=%s meds=%d fingerprint=%s",
            guide.id,
            profile_id,
            prescription_group_id,
            len(meds),
            fingerprint[:12],
        )
        return guide

    # ── SSE 스트림 ─────────────────────────────────────────────────────────
    # 흐름: deadline 설정 -> tick 마다 DB 조회 -> status 변경 시 yield
    #       -> terminal/timeout 도달 시 close
    async def stream_guide_states(
        self,
        guide_id: UUID | str,
        account_id: UUID,
        *,
        max_seconds: int = _STREAM_MAX_SECONDS,
        tick_seconds: float = _STREAM_TICK_SECONDS,
    ) -> AsyncIterator[str]:
        r"""SSE 스트림 — guide status 변화 시점마다 event yield.

        - 첫 호출 즉시 1회 update event.
        - terminal (ready / no_active_meds / failed) 도달 시 close.
        - ``max_seconds`` 도달 시 timeout event 후 close.
        - guide 가 사라지면 error event 후 close.

        Args:
            guide_id: 스트리밍할 guide ID.
            account_id: ownership 검증용 (소유자 아니면 error 후 close).
            max_seconds: 단일 SSE 연결 최대 유지 시간.
            tick_seconds: DB 재조회 주기.

        Yields:
            ``"event: <name>\\ndata: <json>\\n\\n"`` 형식의 SSE chunk.
        """
        deadline = time.monotonic() + max_seconds
        last_status: str | None = None
        while True:
            guide = await self.guide_repo.get_by_id(guide_id)  # type: ignore[arg-type]
            if guide is None:
                yield _sse_event("error", {"detail": "Guide not found."})
                return
            if not await self._is_owned_by(guide, account_id):
                yield _sse_event("error", {"detail": "Access denied."})
                return

            payload = _to_sse_payload(guide)
            if guide.status != last_status:
                yield _sse_event("update", payload)
                last_status = guide.status

            if guide.status != LifestyleGuideStatus.PENDING.value:
                return
            if time.monotonic() >= deadline:
                yield _sse_event("timeout", {"status": guide.status})
                return
            await asyncio.sleep(tick_seconds)

    # ── ownership helpers ─────────────────────────────────────────────────
    async def _verify_profile_ownership(self, profile_id: UUID, account_id: UUID) -> None:
        profile = await self.profile_repo.get_by_id(profile_id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        if profile.account_id != account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this profile.")

    async def _verify_guide_ownership(self, guide: LifestyleGuide, account_id: UUID) -> None:
        if not await self._is_owned_by(guide, account_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this guide.")

    async def _is_owned_by(self, guide: LifestyleGuide, account_id: UUID) -> bool:
        profile = await self.profile_repo.get_by_id(guide.profile_id)
        return bool(profile and profile.account_id == account_id)

    # ── 외부 API ──────────────────────────────────────────────────────────
    async def enqueue_guide_with_owner_check(
        self,
        profile_id: UUID,
        prescription_group_id: UUID,
        account_id: UUID,
    ) -> LifestyleGuide:
        """생성 요청 — profile 소유 확인 후 처방전 단위 enqueue.

        Args:
            profile_id: 가이드 받을 프로필 UUID.
            prescription_group_id: 가이드를 만들 처방전 그룹 UUID.
            account_id: 인증된 호출자 계정 UUID.

        Returns:
            ``LifestyleGuide`` — pending 또는 dedupe hit 의 ready.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.enqueue_guide_generation(profile_id, prescription_group_id)

    async def get_guide_with_owner_check(self, guide_id: UUID, account_id: UUID) -> LifestyleGuide:
        """Fetch one guide with ownership check.

        Args:
            guide_id: Target guide UUID.
            account_id: Requesting account UUID.

        Returns:
            LifestyleGuide instance owned by ``account_id``.

        Raises:
            HTTPException: 404 if not found, 403 if owned by another account.
        """
        guide = await self.guide_repo.get_by_id(guide_id)
        if not guide:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lifestyle guide not found.")
        await self._verify_guide_ownership(guide, account_id)
        return guide

    async def get_latest_guide_with_owner_check(
        self,
        profile_id: UUID,
        account_id: UUID,
    ) -> LifestyleGuide:
        """Return the most recent guide of ``profile_id`` after ownership check.

        Args:
            profile_id: Owner profile UUID.
            account_id: Requesting account UUID.

        Returns:
            Most recent LifestyleGuide for the profile.

        Raises:
            HTTPException: 404 if no guide exists, 403 if profile not owned.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        guide = await self.guide_repo.get_latest_by_profile(profile_id)
        if not guide:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No lifestyle guide found for this profile.",
            )
        return guide

    async def list_guides_with_owner_check(
        self,
        profile_id: UUID,
        account_id: UUID,
    ) -> list[LifestyleGuide]:
        """List all guides of ``profile_id`` after ownership check.

        Args:
            profile_id: Owner profile UUID.
            account_id: Requesting account UUID.

        Returns:
            All guides for the profile (newest first).
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.guide_repo.get_all_by_profile(profile_id)

    async def delete_guide_with_owner_check(self, guide_id: UUID, account_id: UUID) -> None:
        """가이드 삭제 — 그 가이드에서 나온 챌린지도 진행 중·완료분까지 함께 사라진다."""
        guide = await self.get_guide_with_owner_check(guide_id, account_id)
        await self._cascade_delete_guide(guide)
        logger.info("[GUIDE] 가이드 삭제 완료 guide_id=%s account_id=%s", guide_id, account_id)

    async def _cascade_delete_guide(self, guide: LifestyleGuide) -> None:
        """단일 가이드 삭제 — 그 가이드에서 나온 챌린지도 함께 사라진다.

        ⚠️ 2026-09-15 정책 변경(QA-01). 이전에는 **활성·완료 챌린지를
        ``guide_id=None`` 으로 분리 보존**하고 미시작만 지웠다(사용자 진행분 유지).
        사용자 결정으로 **진행분까지 삭제**하는 것으로 바꿨다 — 삭제 의미론을
        hard delete 로 통일하는 흐름의 일부다.

        구현은 **FK 에 맡긴다**: ``challenges.guide_id`` 가 ``ON DELETE CASCADE`` 라
        가이드 행을 지우면 DB 가 자식 챌린지를 함께 지운다. 손으로 도는 루프는
        같은 일을 두 번 하는 것이었고, 실제로 그 중복이 QA-01(soft delete 가 FK
        cascade 에 덮이는 문제)의 원인이었다.

        사용자가 직접 만든 챌린지는 ``guide_id`` 가 NULL 이라 영향받지 않는다.

        Args:
            guide: 삭제 대상 LifestyleGuide.
        """
        await self.guide_repo.delete_by_id(guide.id)

    async def cascade_delete_active_guides_by_profile(self, profile_id: UUID) -> int:
        """프로필의 모든 active 가이드 일괄 cascade 삭제.

        처방전 그룹 삭제 흐름에서 호출 — 약 그룹이 사라지면 그 시점 기준의
        가이드도 의미가 흐려지므로 함께 정리. 각 가이드의 챌린지는
        ``_cascade_delete_guide`` 와 동일하게 **함께 물리 삭제**된다.

        Args:
            profile_id: 대상 프로필 UUID.

        Returns:
            정리된 가이드 수.
        """
        guides = await self.guide_repo.get_all_by_profile(profile_id)
        for g in guides:
            await self._cascade_delete_guide(g)
        return len(guides)

    # ── "추천 챌린지 더 보기" (LLM 호출 X — 단일 UPDATE) ───────────────────
    # 흐름: ownership 확인 -> ready 검증 -> revealed < 15 검증
    #       -> revealed_challenge_count += 5 (단일 UPDATE) -> 갱신된 가이드 반환
    # 정책: 가이드 생성 시 LLM 으로 한 번에 15개를 받아 DB 저장. 사용자에게는
    #       5개씩 점진 노출. "더 보기" 는 노출 카운트만 늘리므로 비용 0,
    #       챌린지 일관성 보존, 한도 검증 단순.
    async def reveal_more_challenges_with_owner_check(
        self,
        guide_id: UUID,
        account_id: UUID,
    ) -> LifestyleGuide:
        """가이드의 노출 챌린지 수를 5개 더 늘려 반환 (LLM 호출 없음).

        Args:
            guide_id: 대상 가이드 UUID.
            account_id: 인증된 호출자 계정 UUID.

        Returns:
            ``LifestyleGuide`` — ``revealed_challenge_count`` 가 +5 된 상태.

        Raises:
            HTTPException 404/403: 가이드 미존재 / 소유자 불일치.
            HTTPException 409 (GUIDE_NOT_READY): 가이드가 ready 상태가 아님.
            HTTPException 409 (REVEAL_LIMIT_REACHED): 이미 15개 모두 노출됨.
        """
        guide = await self.get_guide_with_owner_check(guide_id, account_id)
        if guide.status != LifestyleGuideStatus.READY.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "GUIDE_NOT_READY",
                    "message": "가이드가 아직 준비되지 않아 추천을 더 받을 수 없어요.",
                },
            )
        if guide.revealed_challenge_count >= _TOTAL_CHALLENGES:
            limit_msg = f"더 이상 추천받을 수 없어요. 한 가이드에서 최대 {_TOTAL_CHALLENGES}개까지 추천받을 수 있어요."
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "REVEAL_LIMIT_REACHED",
                    "message": limit_msg,
                    "total": _TOTAL_CHALLENGES,
                    "revealed": guide.revealed_challenge_count,
                },
            )
        new_revealed = min(guide.revealed_challenge_count + _REVEAL_STEP, _TOTAL_CHALLENGES)
        await self.guide_repo.set_revealed_challenge_count(guide.id, new_revealed)
        guide.revealed_challenge_count = new_revealed
        logger.info(
            "[GUIDE] reveal more guide_id=%s account_id=%s revealed=%d/%d",
            guide_id,
            account_id,
            new_revealed,
            _TOTAL_CHALLENGES,
        )
        return guide

    async def get_guide_challenges_with_owner_check(
        self,
        guide_id: UUID,
        account_id: UUID,
    ) -> list[Challenge]:
        """List challenges associated with a guide after ownership check.

        가이드에 연결된 챌린지는 LLM 으로 한 번에 15개가 만들어져 있다. FE 는
        이를 5개씩 페이지네이션 (1/3, 2/3, 3/3) 으로 노출하므로 BE 는 항상 전체
        15개를 반환한다.

        Args:
            guide_id: Source guide UUID.
            account_id: Requesting account UUID.

        Returns:
            Challenges linked to the guide (전체 — 보통 15개).

        Raises:
            HTTPException: 404 if guide missing, 403 if owned by another account.
        """
        guide = await self.guide_repo.get_by_id(guide_id)
        if not guide:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lifestyle guide not found.")
        await self._verify_guide_ownership(guide, account_id)
        return await self.challenge_repo.get_by_guide_id(guide.id)


def _to_sse_payload(guide: LifestyleGuide) -> dict[str, Any]:
    """SSE update event 의 data — LifestyleGuideResponse 와 호환되는 dict."""
    return {
        "id": str(guide.id),
        "profile_id": str(guide.profile_id),
        "status": guide.status,
        "content": guide.content or {},
        "medication_snapshot": guide.medication_snapshot or [],
        "revealed_challenge_count": getattr(guide, "revealed_challenge_count", 5),
        "created_at": guide.created_at.isoformat() if guide.created_at else None,
        "processed_at": guide.processed_at.isoformat() if guide.processed_at else None,
    }


def _sse_event(event_name: str, data: dict[str, Any]) -> str:
    r"""SSE 한 event 를 직렬화 — ``event:`` + ``data:`` + ``\n\n`` 종료."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_name}\ndata: {payload}\n\n"
