"""LLM 응답 파싱·로깅 공통 텍스트 헬퍼.

여러 도메인 (RAG 응답 생성, 세션 요약, 쿼리 재작성) 이 공통으로 쓰는
짧은 텍스트 처리 함수들. 도메인별 모듈에 중복 정의하지 않는다.
"""

from app.dtos.rag import TokenUsage


def sanitize_error_message(message: str, limit: int = 120) -> str:
  """에러 메시지를 한 줄 로그용으로 정리한다.

  Args:
      message: 원본 예외 메시지.
      limit: 최대 길이 (초과 시 ``...`` 로 트렁케이션).

  Returns:
      공백이 정규화되고 길이가 제한된 한 줄 문자열.
  """
  cleaned = " ".join(message.split())
  if len(cleaned) <= limit:
    return cleaned
  return cleaned[:limit] + "..."


def strip_quote_wrapping(text: str) -> str:
  """LLM 응답에서 외곽 따옴표(쌍따옴표/홑따옴표)를 제거한다.

  Args:
      text: 원본 LLM 응답 문자열.

  Returns:
      외곽 따옴표가 제거되고 strip 된 문자열.
  """
  stripped = text.strip()
  if len(stripped) < 2:
    return stripped
  if stripped[0] == stripped[-1] and stripped[0] in ('"', "'"):
    return stripped[1:-1].strip()
  return stripped


def strip_code_fence(text: str) -> str:
  """LLM 응답을 감싼 외곽 ``` 코드펜스를 제거한다.

  Idempotent — 펜스가 없으면 그대로 strip 만 적용. Phase Z 요약 응답이
  DB 에 저장될 때 ``` markdown ... ``` 같은 wrapper 가 섞이지 않도록
  방어적으로 사용한다.

  Args:
      text: 원본 LLM 응답.

  Returns:
      외곽 펜스가 제거되고 strip 된 본문.
  """
  stripped = text.strip()
  if not stripped.startswith("```"):
    return stripped

  first_newline = stripped.find("\n")
  if first_newline == -1:
    return stripped

  body = stripped[first_newline + 1 :]
  if body.rstrip().endswith("```"):
    body = body.rstrip()[: -len("```")]
  return body.strip()


def format_token_usage(usage: TokenUsage | None) -> str:
  """토큰 사용량을 로그 한 줄에 들어갈 짧은 표기로 변환한다.

  Args:
      usage: 응답에 포함된 토큰 사용량 DTO. ``None`` 가능.

  Returns:
      ``"total(prompt+completion)"`` 형태 문자열, 없으면 ``"?"``.
  """
  if usage is None:
    return "?"
  return f"{usage.total_tokens}({usage.prompt_tokens}+{usage.completion_tokens})"
