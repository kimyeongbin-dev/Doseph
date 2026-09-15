"""OCR API router module.

본 라우터는 HTTP I/O 만 담당한다. CLOVA OCR 호출과 약품 매칭은
ai-worker 의 ``process_ocr_task`` 가 비동기로 처리하며, 결과는 DB
``ocr_drafts`` 테이블에 영속 저장된다 (Redis 미사용).

흐름:
1. ``POST /ocr/extract`` -> 즉시 200 + draft_id (medicines=[])
2. ``GET  /ocr/draft/{id}`` -> status (pending/ready/no_text/...) + medicines
3. ``GET  /ocr/drafts/active`` -> main 페이지 카드용 활성 draft 목록
4. ``POST /ocr/confirm`` -> ocr_drafts.consumed_at 설정 + medications INSERT
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.dependencies.security import get_current_account
from app.dtos.ocr import (
    ConfirmMedicationRequest,
    OcrActiveDraftsResponse,
    OcrDraftPollResponse,
    OcrExtractResponse,
)
from app.models.accounts import Account
from app.models.profiles import Profile, RelationType
from app.services.ocr_service import OCRService

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # nginx 가 SSE chunk 를 buffer 하지 않도록
}

router = APIRouter(
    prefix="/ocr",
    tags=["AI Integration"],
    dependencies=[Depends(get_current_account)],
)

ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def get_ocr_service() -> OCRService:
    """OCRService 인스턴스를 반환 (의존성 주입용)."""
    return OCRService()


async def get_owned_profile_or_self(
    current_account: Annotated[Account, Depends(get_current_account)],
    profile_id: str | None = None,
) -> Profile:
    """선택된 프로필 (profile_id query) 의 ownership 검증 후 반환.

    profile_id 가 주어지면 해당 프로필을 조회하고 current_account 가 소유 중인지
    확인. 미전달 시 SELF 프로필로 fallback (backward compatibility).

    Args:
        current_account: 인증된 계정.
        profile_id: 동작 대상 프로필 UUID (query param). 없으면 SELF 사용.

    Returns:
        ownership 검증을 통과한 Profile.

    Raises:
        HTTPException: profile_id 가 존재하지 않거나 타인 소유면 404.
    """
    if profile_id:
        profile = await Profile.filter(
            id=profile_id,
            account_id=current_account.id,
        ).first()
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found or not owned by current account.",
            )
        return profile
    # fallback: SELF
    profile = await Profile.filter(
        account_id=current_account.id,
        relation_type=RelationType.SELF,
    ).first()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connected user profile information not found.",
        )
    return profile


@router.post(
    "/extract",
    response_model=OcrExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="처방전 이미지 업로드 후 OCR 비동기 처리 시작",
)
async def extract_medication_from_image(
    file: Annotated[UploadFile, File(description="Prescription/medicine bag image to recognize")],
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    profile: Annotated[Profile, Depends(get_owned_profile_or_self)],
) -> OcrExtractResponse:
    """이미지를 ai-worker 로 enqueue 하고 draft_id 를 즉시 반환한다.

    실제 OCR 처리는 ai-worker 의 RQ task 가 비동기로 수행해 ``ocr_drafts`` 테이블을
    UPDATE 한다. 프론트는 응답으로 받은 ``draft_id`` 로 ``/ocr/draft/{id}`` 를 폴링.

    같은 사용자 + 같은 image_hash + 미consume draft 가 이미 있으면 dedup 으로
    기존 draft_id 가 반환된다 (RQ 재enqueue 없음).

    Args:
        file: 업로드된 처방전/약봉투 이미지 파일.
        ocr_service: OCR 서비스 인스턴스.
        profile: 요청자의 SELF 프로필 (의존성).

    Returns:
        ``OcrExtractResponse`` — ``draft_id`` 와 빈 ``medicines`` 리스트.

    Raises:
        HTTPException: 형식 미지원·크기 초과·파일 누락.
    """
    _validate_upload(file)
    await file.seek(0)
    return await ocr_service.enqueue_ocr_task(file, profile.id)


def _validate_upload(file: UploadFile) -> None:
    """업로드 파일의 형식·크기를 검증한다."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file format.")
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size too large. (Max: {MAX_FILE_SIZE // (1024 * 1024)}MB)",
        )


@router.get(
    "/drafts/active",
    response_model=OcrActiveDraftsResponse,
    summary="현재 사용자의 활성 OCR draft 목록 (main 페이지 카드용)",
)
async def list_active_drafts(
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    profile: Annotated[Profile, Depends(get_owned_profile_or_self)],
) -> OcrActiveDraftsResponse:
    """24h 안 + 미consume 인 draft 들을 최신순으로 반환한다.

    빈 리스트일 수 있다 (초기 사용자, 모두 consume 됨, 24h 경과). 빈 리스트는
    에러가 아니라 정상 응답 — main 페이지가 카드를 숨기는 신호로 사용한다.
    """
    return await ocr_service.list_active_drafts(profile.id)


@router.get(
    "/draft/{draft_id}",
    response_model=OcrDraftPollResponse,
    summary="OCR 처리 결과 폴링 (status + medicines)",
)
async def get_draft_medication(
    draft_id: str,
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    profile: Annotated[Profile, Depends(get_owned_profile_or_self)],
) -> OcrDraftPollResponse:
    """폴링 — DB 에서 draft 의 status / medicines 를 조회한다.

    응답의 ``status`` 가 ``pending`` 이면 프론트는 다시 폴링하고, ``ready`` 면
    ``medicines`` 가 채워져 있다. 그 외(``no_text``, ``no_candidates``,
    ``failed``)는 사용자에게 안내 메시지를 보여준다.

    Args:
        draft_id: enqueue 응답의 draft_id.
        ocr_service: OCR 서비스 인스턴스.
        profile: 요청자의 SELF 프로필 (ownership 검증용).

    Returns:
        ``OcrDraftPollResponse``.

    Raises:
        HTTPException: draft 가 없거나 타인 소유 (404).
    """
    response = await ocr_service.get_draft_data(draft_id, profile.id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return response


@router.get(
    "/draft/{draft_id}/stream",
    summary="OCR 처리 결과 SSE 스트림 (long-poll, status 변화만 push)",
)
async def stream_draft_medication(
    draft_id: str,
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    profile: Annotated[Profile, Depends(get_owned_profile_or_self)],
) -> StreamingResponse:
    """SSE 로 status 변화를 push 한다.

    클라이언트는 ``EventSource`` 또는 ``fetch().body.getReader()`` 로 수신한다.
    이벤트 종류:

    - ``update`` : status 가 변할 때마다 (첫 호출은 즉시 1회). data = OcrDraftPollResponse JSON.
    - ``timeout``: 단일 연결 max_seconds 초과 시. 클라이언트가 재연결하도록 유도.
    - ``error`` : draft 가 사라졌을 때 (만료 등).
    """
    return StreamingResponse(
        ocr_service.stream_draft_states(draft_id, profile.id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.delete(
    "/draft/{draft_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="검수 화면에서 draft 폐기 (다시 촬영 흐름)",
)
async def discard_draft(
    draft_id: str,
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    profile: Annotated[Profile, Depends(get_owned_profile_or_self)],
) -> None:
    """Soft delete — consumed_at 을 설정해 active 목록·dedup 에서 제외한다.

    이미 폐기·만료·타인 소유인 경우에도 204 로 응답 (idempotent). 프론트는
    응답 본문 없이 단순 "처리 완료" 로 간주하고 다음 화면으로 이동.
    """
    await ocr_service.discard_draft(draft_id, profile.id)


@router.post(
    "/confirm",
    status_code=status.HTTP_201_CREATED,
    summary="검수 완료 약품 메타를 DB 에 영구 저장",
)
async def confirm_and_save_medication(
    request: ConfirmMedicationRequest,
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    profile: Annotated[Profile, Depends(get_owned_profile_or_self)],
) -> dict:
    """사용자가 검수·수정한 최종 약품 리스트를 DB 에 저장한다."""
    try:
        return await ocr_service.confirm_and_save(request, profile.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
