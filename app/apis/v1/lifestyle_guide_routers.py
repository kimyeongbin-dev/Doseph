"""Lifestyle guide API router module.

라우팅 흐름은 OCR 와 동일한 RQ producer + SSE long-poll 패턴을 따른다:

1. ``POST /lifestyle-guides/generate`` -> 202 Accepted + pending guide_id
2. ``GET  /lifestyle-guides/{guide_id}/stream`` -> SSE (status 변화 push)
3. ``GET  /lifestyle-guides/{guide_id}`` -> 단발 폴링 (legacy 호환)
4. 기타 list/latest/delete/challenges 는 기존과 동일.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.dependencies.security import get_current_account
from app.dtos.challenge import ChallengeResponse
from app.dtos.lifestyle_guide import (
    GuideDeleteImpactResponse,
    LifestyleGuidePendingResponse,
    LifestyleGuideResponse,
)
from app.models.accounts import Account
from app.services.lifestyle_guide_service import LifestyleGuideService

router = APIRouter(prefix="/lifestyle-guides", tags=["Lifestyle Guides"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # nginx 가 SSE chunk 를 buffer 하지 않도록
}


def get_lifestyle_guide_service() -> LifestyleGuideService:
    """LifestyleGuideService 인스턴스 (DI)."""
    return LifestyleGuideService()


# Type aliases for dependency injection
LifestyleGuideServiceDep = Annotated[LifestyleGuideService, Depends(get_lifestyle_guide_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


# ── POST /lifestyle-guides/generate (RQ enqueue, 처방전 단위) ─────────────
# 흐름: ownership 검증 -> 처방전 그룹의 active medications + Profile.health_survey
#       -> fingerprint 산출 -> 동일 fingerprint ready 가이드 존재 시 즉시 반환
#       -> 없으면 pending row INSERT (group_id 기록) + RQ enqueue -> 202
@router.post(
    "/generate",
    response_model=LifestyleGuidePendingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue lifestyle guide generation (async, 처방전 단위)",
)
async def enqueue_guide(
    profile_id: UUID,
    prescription_group_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> LifestyleGuidePendingResponse:
    """처방전 그룹 단위로 라이프스타일 가이드 생성을 비동기 등록한다.

    LLM 호출은 ai-worker 가 수행하므로 이 엔드포인트는 즉시 반환한다.
    프론트는 응답 ``id`` 로 ``GET /lifestyle-guides/{id}/stream`` SSE 를 연다.

    fingerprint 는 (그룹의 active medications + Profile.health_survey + 프롬프트
    버전) 의 sha256 — 같은 입력 = 같은 가이드 본문 (dedupe).

    Args:
        profile_id: 가이드 받을 프로필 UUID.
        prescription_group_id: 가이드를 생성할 처방전 그룹 UUID.
        current_account: 인증된 계정.
        service: 라이프스타일 가이드 서비스.

    Returns:
        ``LifestyleGuidePendingResponse`` — pending guide id + status.
        dedupe hit 이면 status='ready' 로 즉시 반환되어 FE 가 SSE 를 건너뛴다.

    Raises:
        HTTPException 404/403: 처방전 그룹 존재 X / 소유자 불일치.
        HTTPException 409 (NO_ACTIVE_MEDICATIONS): 그룹 내 복용 중 약 0건 —
            ``detail`` 에 ``code`` / ``message`` / ``redirect_to=/medication``
            포함되어 FE 가 토스트 + 라우팅 처리.
    """
    guide = await service.enqueue_guide_with_owner_check(
        profile_id,
        prescription_group_id,
        current_account.id,
    )
    return LifestyleGuidePendingResponse(id=guide.id, status=guide.status)


# ── GET /lifestyle-guides/{guide_id}/stream (SSE long-poll) ──────────────
# 흐름: ownership 은 stream 내부에서 검증 -> StreamingResponse 즉시 반환
@router.get(
    "/{guide_id}/stream",
    summary="라이프스타일 가이드 SSE 스트림 (status 변화만 push)",
)
async def stream_guide(
    guide_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> StreamingResponse:
    """SSE 로 가이드 생성 진행 상태를 push 한다.

    이벤트:

    - ``update`` : status 변화 시 (첫 호출은 즉시 1회). data = LifestyleGuideResponse JSON.
    - ``timeout``: 단일 연결 max_seconds 초과 시. 클라이언트가 재연결.
    - ``error`` : guide 가 사라졌거나 ownership 위반.
    """
    return StreamingResponse(
        service.stream_guide_states(guide_id, current_account.id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get(
    "/latest",
    response_model=LifestyleGuideResponse,
    summary="Get latest lifestyle guide",
)
async def get_latest_guide(
    profile_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> LifestyleGuideResponse:
    """프로필의 가장 최근 가이드 (status 무관)."""
    guide = await service.get_latest_guide_with_owner_check(profile_id, current_account.id)
    return LifestyleGuideResponse.model_validate(guide)


@router.get(
    "",
    response_model=list[LifestyleGuideResponse],
    summary="List lifestyle guides",
)
async def list_guides(
    profile_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> list[LifestyleGuideResponse]:
    """프로필의 모든 가이드를 newest-first 로 반환."""
    guides = await service.list_guides_with_owner_check(profile_id, current_account.id)
    return [LifestyleGuideResponse.model_validate(g) for g in guides]


@router.get(
    "/{guide_id}",
    response_model=LifestyleGuideResponse,
    summary="Get lifestyle guide details",
)
async def get_guide(
    guide_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> LifestyleGuideResponse:
    """단발 폴링 — SSE 안 쓰고 한 번만 status/content 를 받고 싶을 때."""
    guide = await service.get_guide_with_owner_check(guide_id, current_account.id)
    return LifestyleGuideResponse.model_validate(guide)


# ── GET /lifestyle-guides/{guide_id}/delete-impact ───────────────────────
# 흐름: 소유권 검증 -> 동반 삭제될 챌린지 상태별 집계 -> 건수 반환
# 삭제 확인 다이얼로그가 "무엇을 잃는지"를 보여주기 위해 누르기 전에 호출한다.
@router.get(
    "/{guide_id}/delete-impact",
    response_model=GuideDeleteImpactResponse,
    summary="가이드 삭제 시 함께 사라질 챌린지 수",
)
async def get_guide_delete_impact(
    guide_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> GuideDeleteImpactResponse:
    """가이드를 지우면 함께 삭제될 챌린지를 상태별로 센다.

    진행 중·완료 챌린지도 함께 사라지므로(완료 날짜·streak 소실) 삭제 전에
    이 값을 보여준다. 사용자가 직접 만든 챌린지는 영향받지 않아 집계 밖이다.
    """
    return await service.get_delete_impact_with_owner_check(guide_id, current_account.id)


@router.delete(
    "/{guide_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete lifestyle guide",
)
async def delete_guide(
    guide_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> None:
    """가이드 삭제. 그 가이드에서 나온 챌린지는 **진행 중·완료분까지 함께 물리 삭제**된다.

    사용자가 직접 만든 챌린지(``guide_id`` 가 NULL)는 영향받지 않는다.
    """
    await service.delete_guide_with_owner_check(guide_id, current_account.id)


@router.get(
    "/{guide_id}/challenges",
    response_model=list[ChallengeResponse],
    summary="List guide challenges",
)
async def get_guide_challenges(
    guide_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> list[ChallengeResponse]:
    """해당 가이드에서 만들어진 챌린지 목록."""
    challenges = await service.get_guide_challenges_with_owner_check(guide_id, current_account.id)
    return [ChallengeResponse.model_validate(c) for c in challenges]


# ── POST /lifestyle-guides/{guide_id}/reveal-more-challenges ─────────────
# 흐름: ownership + ready + revealed<15 검증
#       -> revealed_challenge_count += 5 (단일 UPDATE, LLM 호출 X)
#       -> 200 + 갱신된 가이드 반환
# 정책: 가이드 생성 시 LLM 으로 한 번에 15개를 받아 DB 저장. 본 엔드포인트는
#       *노출 카운트만* 늘려 사용자가 5개씩 점진적으로 챌린지를 보게 함.
#       LLM 비용 0, 챌린지 일관성 보존, 한도 = 15.
@router.post(
    "/{guide_id}/reveal-more-challenges",
    response_model=LifestyleGuideResponse,
    summary="추천 챌린지 더 보기 (LLM 호출 X — 노출 카운트만 +5, 최대 15개)",
)
async def reveal_more_guide_challenges(
    guide_id: UUID,
    current_account: CurrentAccount,
    service: LifestyleGuideServiceDep,
) -> LifestyleGuideResponse:
    """가이드 본문/챌린지 set 모두 그대로, 노출 카운트만 5개 늘린다.

    - 가이드 생성 시점에 LLM 이 이미 15개를 모두 만들어 DB 에 저장돼 있다.
      본 엔드포인트는 사용자에게 점진 노출하기 위한 단순 카운터 +5.
    - 한도: 15. 초과 호출 시 409 ``REVEAL_LIMIT_REACHED``.
    - FE 는 응답의 ``revealed_challenge_count`` 로 한도 표시 (5/10/15).
      챌린지 list 는 ``GET /lifestyle-guides/{id}/challenges`` 의 앞 N 개만
      렌더 (정렬 기준은 challenge_repo.get_by_guide_id 의 안정 정렬).
    """
    guide = await service.reveal_more_challenges_with_owner_check(guide_id, current_account.id)
    return LifestyleGuideResponse.model_validate(guide)
