"""처방전 OCR 텍스트 업로드 — 요청 DTO · 서비스 enqueue · 라우터 계약.

브라우저가 기기 안에서 OCR 을 돌리고 «약 줄» 글자만 보내므로, 서버는 이미지를
받지 않는다. 이 파일은 그 경계를 잠근다:

- 요청 본문은 ``{"text": ...}`` 하나뿐이다(이미지·파일명 같은 다른 필드는 거부).
- 빈 글자·공백만·상한을 넘는 글자는 엣지에서 거부한다.
- 같은 프로필이 같은 글자를 다시 보내면 새 작업 없이 기존 draft 를 돌려준다.
- multipart 이미지 업로드는 더 이상 받지 않는다.

검증 실패는 422 가 아니라 400 이다 — 앱 전역 핸들러(``validation_exception_handler``)가 바꾼다.
"""

from collections.abc import AsyncGenerator
import hashlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest
import pytest_asyncio

from app.apis.v1.ocr_routers import get_ocr_service, get_owned_profile_or_self
from app.dependencies.security import get_current_account
from app.dtos.ocr import OCR_TEXT_MAX_LENGTH, OcrExtractResponse, OcrTextUploadRequest
from app.main import app
from app.services.ocr_service import _OCR_JOB_REF, OCRService

_DRUG_LINES = "642200380 판토복정 40밀리그램 1 3 1\n용법 식후30분에복용하십시오."


def _sha256(text: str) -> str:
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── 요청 DTO — 엣지 검증 ────────────────────────────────────────────


class TestOcrTextUploadRequest:
  """``OcrTextUploadRequest`` 는 글자 하나만 받고, 비었거나 너무 길면 거부한다."""

  def test_accepts_drug_lines(self) -> None:
    assert OcrTextUploadRequest(text=_DRUG_LINES).text == _DRUG_LINES

  @pytest.mark.parametrize("text", ["", "   ", "\n\t \n"])
  def test_rejects_empty_or_blank(self, text: str) -> None:
    with pytest.raises(ValidationError):
      OcrTextUploadRequest(text=text)

  def test_accepts_exactly_max_length(self) -> None:
    text = "가" * OCR_TEXT_MAX_LENGTH
    assert OcrTextUploadRequest(text=text).text == text

  def test_rejects_over_max_length(self) -> None:
    with pytest.raises(ValidationError):
      OcrTextUploadRequest(text="가" * (OCR_TEXT_MAX_LENGTH + 1))

  def test_rejects_extra_fields(self) -> None:
    """이미지·파일명을 같이 실어 보내면 거부한다 — 서버는 글자 외에 받지 않는다."""
    with pytest.raises(ValidationError):
      OcrTextUploadRequest.model_validate({"text": _DRUG_LINES, "image": "data:image/png;base64,AAAA"})


# ── 서비스 — 글자 해시로 중복을 가르고 글자만 큐에 싣는다 ──────────────


def _service(existing: object | None = None) -> tuple[OCRService, MagicMock, MagicMock]:
  """RQ·DB 를 만들지 않는 서비스 — 저장소와 큐를 가짜로 끼운다."""
  service = OCRService.__new__(OCRService)
  repo = MagicMock()
  repo.find_active_by_hash = AsyncMock(return_value=existing)
  repo.create_pending = AsyncMock(return_value=MagicMock(id=uuid4()))
  queue = MagicMock()
  service._repository = repo
  service._queue = queue
  return service, repo, queue


class TestEnqueueOcrText:
  """``OCRService.enqueue_ocr_text`` — 새 글자면 draft 를 만들어 enqueue, 같은 글자면 재사용."""

  @pytest.mark.asyncio
  async def test_new_text_creates_draft_and_enqueues_text_only(self) -> None:
    service, repo, queue = _service()
    profile_id = uuid4()

    result = await service.enqueue_ocr_text(_DRUG_LINES, profile_id)

    draft = repo.create_pending.return_value
    repo.find_active_by_hash.assert_awaited_once_with(profile_id, _sha256(_DRUG_LINES))
    repo.create_pending.assert_awaited_once_with(profile_id, _sha256(_DRUG_LINES))
    queue.enqueue.assert_called_once_with(_OCR_JOB_REF, _DRUG_LINES, str(draft.id))
    assert result == OcrExtractResponse(draft_id=str(draft.id), medicines=[])

  @pytest.mark.asyncio
  async def test_same_text_reuses_active_draft(self) -> None:
    existing = MagicMock(id=uuid4())
    service, repo, queue = _service(existing=existing)

    result = await service.enqueue_ocr_text(_DRUG_LINES, uuid4())

    assert result.draft_id == str(existing.id)
    repo.create_pending.assert_not_awaited()
    queue.enqueue.assert_not_called()


# ── 라우터 — JSON 글자는 받고, 이미지 업로드는 받지 않는다 ─────────────


@pytest_asyncio.fixture
async def ocr_client() -> AsyncGenerator[tuple[AsyncClient, MagicMock]]:
  """인증·프로필·서비스를 가짜로 바꾼 클라이언트."""
  fake_service = MagicMock()
  fake_service.enqueue_ocr_text = AsyncMock(return_value=OcrExtractResponse(draft_id=str(uuid4()), medicines=[]))
  profile = MagicMock(id=uuid4())
  app.dependency_overrides[get_current_account] = lambda: MagicMock(id=uuid4())
  app.dependency_overrides[get_owned_profile_or_self] = lambda: profile
  app.dependency_overrides[get_ocr_service] = lambda: fake_service
  try:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
      yield ac, fake_service
  finally:
    for dep in (get_current_account, get_owned_profile_or_self, get_ocr_service):
      app.dependency_overrides.pop(dep, None)


class TestExtractRoute:
  """``POST /api/v1/ocr/extract`` 의 요청 모양."""

  @pytest.mark.asyncio
  async def test_json_text_is_enqueued(self, ocr_client: tuple[AsyncClient, MagicMock]) -> None:
    client, fake_service = ocr_client

    response = await client.post("/api/v1/ocr/extract", json={"text": _DRUG_LINES})

    assert response.status_code == 200
    assert fake_service.enqueue_ocr_text.await_args.args[0] == _DRUG_LINES

  @pytest.mark.asyncio
  async def test_blank_text_is_rejected(self, ocr_client: tuple[AsyncClient, MagicMock]) -> None:
    client, fake_service = ocr_client

    response = await client.post("/api/v1/ocr/extract", json={"text": "  "})

    assert response.status_code == 400
    fake_service.enqueue_ocr_text.assert_not_awaited()

  @pytest.mark.asyncio
  async def test_rejected_text_is_not_echoed(self, ocr_client: tuple[AsyncClient, MagicMock]) -> None:
    """검증 오류 응답에 보낸 글자를 되돌려 싣지 않는다."""
    client, _ = ocr_client

    response = await client.post("/api/v1/ocr/extract", json={"text": "가" * (OCR_TEXT_MAX_LENGTH + 1)})

    assert response.status_code == 400
    assert response.json()["details"], "오류 내역이 비면 아래 단언은 아무것도 못 본다"
    assert "가가가" not in response.text

  @pytest.mark.asyncio
  async def test_image_upload_is_rejected(self, ocr_client: tuple[AsyncClient, MagicMock]) -> None:
    client, fake_service = ocr_client

    response = await client.post(
      "/api/v1/ocr/extract",
      files={"file": ("rx.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )

    assert response.status_code == 400
    fake_service.enqueue_ocr_text.assert_not_awaited()
