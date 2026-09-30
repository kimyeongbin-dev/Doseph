"""CLOVA OCR API 호출.

이미지 bytes 한 장을 받아 NAVER CLOVA OCR API 에 동기로 전송하고
``inferText`` 들을 공백으로 이어 붙인 단일 문자열을 반환한다.

본 모듈은 OCR 추출 단일 책임만 담당한다 — 텍스트 후처리는
``text_normalizer`` 가, 최종 약품 매칭은 ``medicine_matcher`` 가 맡는다.

이미지를 디스크에 저장하지 않고 메모리(bytes)만으로 처리하므로 컨테이너 간
공유 볼륨이 필요 없다.
"""

import json
import logging
import time
import uuid

import httpx

from ai_worker.core.config import config

logger = logging.getLogger(__name__)

_OCR_TIMEOUT_SEC = 30.0
_DEFAULT_FORMAT = "jpg"


def extract_text_from_image_bytes(image_bytes: bytes, filename: str) -> str:
  """CLOVA OCR API 를 호출해 이미지 bytes 에서 추출된 텍스트를 반환한다.

  Args:
      image_bytes: 원본 이미지의 raw bytes (FastAPI 가 ``await file.read()`` 한 결과).
      filename: 업로드된 파일명 — CLOVA payload 의 ``name``/``format`` 필드 결정에 사용.

  Returns:
      ``inferText`` 들을 공백으로 연결한 문자열. OCR 결과 없으면 빈 문자열.

  Raises:
      ValueError: CLOVA OCR 환경변수(URL/SECRET) 누락.
      httpx.HTTPStatusError: OCR API 가 4xx/5xx 응답.
  """
  invoke_url, secret_key = _resolve_credentials()
  payload = _build_request_payload(filename)
  response_json = _post_to_clova(invoke_url, secret_key, filename, image_bytes, payload)
  return _join_infer_texts(response_json)


def _resolve_credentials() -> tuple[str, str]:
  """CLOVA OCR URL / SECRET 환경변수를 검증·반환한다."""
  invoke_url = config.CLOVA_OCR_INVOKE_URL
  secret_key = config.CLOVA_OCR_SECRET_KEY
  if not invoke_url or not secret_key:
    raise ValueError("OCR 처리 실패: CLOVA_OCR 설정이 누락되었습니다.")
  return invoke_url, secret_key


def _build_request_payload(filename: str) -> dict:
  """CLOVA OCR 요청 JSON payload 를 만든다."""
  name, ext = _split_filename(filename)
  return {
    "images": [{"format": ext, "name": name}],
    "requestId": str(uuid.uuid4()),
    "version": "V2",
    "timestamp": round(time.time() * 1000),
  }


def _split_filename(filename: str) -> tuple[str, str]:
  """파일명을 (stem, ext) 로 분리. 확장자가 없으면 jpg 로 가정."""
  if "." not in filename:
    return filename or "image", _DEFAULT_FORMAT
  name, _, ext = filename.rpartition(".")
  return (name or "image"), (ext.lower() or _DEFAULT_FORMAT)


def _post_to_clova(
  invoke_url: str,
  secret_key: str,
  filename: str,
  image_bytes: bytes,
  payload: dict,
) -> dict:
  """CLOVA API 로 multipart POST 를 전송하고 JSON 응답을 반환한다."""
  try:
    response = httpx.post(
      invoke_url,
      headers={"X-OCR-SECRET": secret_key},
      data={"message": json.dumps(payload).encode("UTF-8")},
      files=[("file", (filename, image_bytes))],
      timeout=_OCR_TIMEOUT_SEC,
    )
    response.raise_for_status()
    return response.json()
  except httpx.HTTPStatusError:
    logger.exception("CLOVA OCR API error for %s", filename)
    raise
  except Exception:
    logger.exception("CLOVA OCR unexpected error for %s", filename)
    raise


def _join_infer_texts(response_json: dict) -> str:
  """CLOVA 응답의 ``fields[].inferText`` 를 공백으로 이어 붙인다."""
  fields = response_json["images"][0]["fields"]
  return " ".join(field["inferText"] for field in fields)
