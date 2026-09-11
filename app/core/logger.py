"""Logging configuration module.

콘솔(stdout) + 파일 이중 출력. 포맷은 ENV 기반(콘솔·파일 동일):
- local/dev: 사람 형식 ``[ts] [LEVEL] [name:func:line] [req_id] msg`` — 직접 읽기 쉬움
- prod: JSON line — 수집기 파싱/분석(문제 시 JSON 받아 분석), request_id·위치 필드 포함

파일 위치는 ``LOG_DIR`` 환경변수로 결정(default ``/app/logs``). docker-compose
volume 마운트로 호스트에 영속화.

회전 정책:
- 시간(3시간) + 파일당 크기(10MB) 상한 **병행** 회전 (``SizeTimedRotatingFileHandler``)
- 백업 2 + 활성 1 = 3개 동시, 평상시 ~9h 보존

파일로깅 안전장치(메모리·저장공간·보안, CLAUDE.md §9):
- 메모리: 메시지 4000자 트렁케이트(``TruncateFilter``)
- 저장공간: 시간+크기 회전 + (배포측) docker json-file 캡
- 보안: 파일 0o640 / 디렉 0o750, JSON 개행 이스케이프(로그 인젝션 방어),
  호출자가 PII/token/huge payload 를 message 에 넣지 않을 책임
- 모듈별 logger(``getLogger(__name__)`` 호출자 측에서)
"""

from collections.abc import AsyncIterator
import contextlib
import contextvars
from datetime import UTC, datetime
from io import TextIOWrapper
import json
import logging
import logging.handlers
import os
from pathlib import Path
import sys
import time
from typing import override

from app.core.log_safe import ScrubFilter

_LOG_DIR_ENV = "LOG_DIR"
_DEFAULT_LOG_DIR = "/app/logs"
# 시간 기반 회전 — 3h x (활성 1 + 백업 2) = 9h 보존
_ROTATE_WHEN = "H"
_ROTATE_INTERVAL_HOURS = 3
_ROTATE_BACKUP_COUNT = 2
_CONSOLE_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] [%(request_id)s] %(message)s"

# ── 파일로깅 안전 상한 (메모리·저장공간·보안) ─────────────────────────
_MAX_MSG_LEN = 4000  # 단일 메시지 문자 상한 — 초과분 트렁케이트(메모리·저장 폭주 방지)
_MAX_BYTES = 10 * 1024 * 1024  # 파일당 크기 상한 10MB — 시간회전과 병행(런어웨이 단일 파일 비대 방지)
_DIR_MODE = 0o750  # 로그 디렉토리 권한(owner rwx / group rx / other 없음)
_FILE_MODE = 0o640  # 로그 파일 권한(owner rw / group r / other 없음) — world-readable 금지

# ── 요청 컨텍스트 (request_id) ─────────────────────────────────────────
# 요청마다 미들웨어가 설정 -> RequestIdFilter 가 모든 로그에 자동 첨부. 기본 "-".
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    """현재 컨텍스트의 request_id (미설정 시 ``-``)."""
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """JSON line formatter — 한 record 당 한 줄 JSON 출력.

    필드: ts (UTC ISO 8601), level, logger, msg, module, line, exception (있을 때).
    ``logger.exception()`` 호출 시 stack trace 가 ``exception`` 에 포함된다.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# ── 메시지 트렁케이션 필터 (재사용) ───────────────────────────────────
# 흐름: 긴 메시지 감지 -> 상한 초과분 잘라 record 재기록 -> 모든 핸들러 공통 적용
# 핸들러에 부착하면 자식 logger 전파 record 에도 적용됨(logger 부착은 전파 미적용).
class TruncateFilter(logging.Filter):
    """단일 로그 메시지를 ``_MAX_MSG_LEN`` 으로 잘라 메모리/저장 폭주를 막는다.

    ``%``-args 를 미리 병합해 ``record.msg`` 에 넣고 ``args`` 를 비운다
    (핸들러마다 재병합 방지, lazy 포맷 결과를 1회만 계산).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if len(message) > _MAX_MSG_LEN:
            dropped = len(message) - _MAX_MSG_LEN
            message = f"{message[:_MAX_MSG_LEN]}…[truncated {dropped} chars]"
        record.msg = message
        record.args = None
        return True


# ── request_id 주입 필터 (재사용) ─────────────────────────────────────
# 흐름: 현재 contextvar 의 request_id -> record.request_id 부착
#       -> 콘솔 포맷(%(request_id)s) / JSON(request_id 필드) 공통 노출
class RequestIdFilter(logging.Filter):
    """현재 컨텍스트의 request_id 를 record 에 부착(모든 핸들러 공통)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


# ── 시간 + 크기 병행 회전 핸들러 (재사용) ──────────────────────────────
# 흐름: 시간 회전(부모) 판단 -> 미해당 시 크기 상한 판단 -> 초과면 회전
#       + 생성 파일은 제한적 권한(_FILE_MODE)으로 오픈(보안).
class SizeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """TimedRotating(시간)에 크기 상한을 더한 회전 핸들러.

    회전 주기 내 런어웨이 로그가 단일 파일을 비대하게 만드는 것을 방지한다.
    """

    def __init__(self, *args: object, max_bytes: int = _MAX_BYTES, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._max_bytes = max_bytes

    @override
    def _open(self) -> TextIOWrapper:
        stream = super()._open()
        with contextlib.suppress(OSError):
            Path(self.baseFilename).chmod(_FILE_MODE)  # world 접근 차단(보안)
        return stream

    @override
    def shouldRollover(self, record: logging.LogRecord) -> int:
        if super().shouldRollover(record):
            return 1
        if self._max_bytes > 0:
            if self.stream is None:
                self.stream = self._open()
            message = f"{self.format(record)}{self.terminator}"
            self.stream.seek(0, os.SEEK_END)
            if self.stream.tell() + len(message.encode("utf-8")) >= self._max_bytes:
                return 1
        return 0


def _is_prod() -> bool:
    """``ENV`` 가 prod 인지 (config 의존 없이 os.environ 직접 참조 — 결합도↓)."""
    return os.environ.get("ENV", "local").strip().lower() == "prod"


def _resolve_log_dir() -> Path:
    """``LOG_DIR`` env 우선, 미설정 시 ``/app/logs``. 디렉토리 idempotent 생성 + 권한 제한."""
    log_dir = Path(os.environ.get(_LOG_DIR_ENV, _DEFAULT_LOG_DIR))
    log_dir.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):  # world 접근 차단(보안). Windows 는 무시됨(무해).
        log_dir.chmod(_DIR_MODE)
    return log_dir


# ── 로거 셋업 (콘솔 + 회전 파일 핸들러) ────────────────────────────────
# 흐름: 기존 핸들러 있으면 재사용 -> 트렁케이션 필터 -> 콘솔 핸들러 부착
#       -> 파일 핸들러(권한제한·시간+크기 회전) 부착 -> 실패 시 콘솔만 폴백
def setup_logger(
    name: str = "app",
    level: int = logging.INFO,
) -> logging.Logger:
    """Set up a logger with console + rotating-file handlers.

    Args:
        name: Logger name for identification. 같은 이름으로 두 번 호출되면
            기존 logger 를 그대로 반환 (handler 중복 방지).
        level: Logging level (default: INFO).

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False  # 루트 logger 로 중복 전달 방지

    # env 기반 포맷: prod=JSON(수집·분석) / local·dev=사람형식(직접 읽기 쉬움).
    # 콘솔·파일 동일 포맷터 사용 — local 파일도 사람형식으로 읽기 쉽게.
    active_formatter: logging.Formatter = JsonFormatter() if _is_prod() else logging.Formatter(_CONSOLE_FORMAT)
    # 필터는 핸들러에 부착(자식 logger 전파 record 에도 적용되도록).
    # 순서: truncate(크기) -> scrub(민감패턴 안전망) -> request_id(컨텍스트).
    # scrub 은 병합·트렁케이트된 최종 메시지에 적용돼야 하므로 truncate 뒤.
    truncate_filter = TruncateFilter()
    scrub_filter = ScrubFilter()
    request_id_filter = RequestIdFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(active_formatter)
    console_handler.addFilter(truncate_filter)
    console_handler.addFilter(scrub_filter)
    console_handler.addFilter(request_id_filter)
    logger.addHandler(console_handler)

    try:
        log_dir = _resolve_log_dir()
        file_handler = SizeTimedRotatingFileHandler(
            log_dir / f"{name}.log",
            when=_ROTATE_WHEN,
            interval=_ROTATE_INTERVAL_HOURS,
            backupCount=_ROTATE_BACKUP_COUNT,
            encoding="utf-8",
            utc=True,
        )
        file_handler.addFilter(truncate_filter)
        file_handler.addFilter(scrub_filter)
        file_handler.addFilter(request_id_filter)
        # 백업 파일 이름에 ISO 타임스탬프 suffix (예: app.log.2026-05-01_15)
        file_handler.suffix = "%Y-%m-%d_%H"
        file_handler.setFormatter(active_formatter)
        logger.addHandler(file_handler)
    except OSError:
        # 파일 시스템 권한 문제 등으로 파일 핸들러 생성 실패 시 콘솔만 유지.
        # 정확한 원인은 콘솔 logger 가 직접 emit (logger 자기 자신에 의존하지 않음).
        logger.warning("Failed to attach TimedRotatingFileHandler — console only", exc_info=True)

    return logger


# ── 전역 예외 핸들러 로깅 헬퍼 (재사용) ────────────────────────────────
# 흐름: 잡은 예외 + 요청 컨텍스트(kind/method/path) -> ERROR 로그(스택 포함)
# 프레임워크 비의존(Request 대신 method/path 문자열) → 단위테스트 용이·재사용.
def log_handled_exception(
    logger: logging.Logger,
    exc: Exception,
    *,
    method: str,
    path: str,
    kind: str,
) -> None:
    """전역 예외 핸들러가 잡은 예외를 요청 컨텍스트 + 스택과 함께 ERROR 기록.

    Args:
        logger: 기록에 사용할 로거.
        exc: 잡힌 예외 인스턴스.
        method: HTTP 메서드(예: GET).
        path: 요청 경로(예: /api/v1/...).
        kind: 분류 라벨(예: ``orm`` / ``db_connection`` / ``unhandled``).
    """
    logger.error("[%s] %s during %s %s", kind, type(exc).__name__, method, path, exc_info=exc)


# ── 외부 경계 관측 로깅 (재사용 async 컨텍스트) ────────────────────────
# 흐름: 진입 DEBUG -> (본문 I/O 실행) -> 성공 INFO(+소요 ms)
#       -> 실패 시 4xx=WARN(설정/클라이언트, 스택 생략)
#          / 그 외=ERROR(5xx·네트워크·버그, 스택 포함), 예외는 원본 그대로 재전파
# 프레임워크·httpx 비의존(status_code 는 getattr 로 추출) — 결합도↓·재사용↑.
# 주의: 호출자는 PII/token 을 operation/context 에 넣지 않을 책임(CLAUDE.md §9).
@contextlib.asynccontextmanager
async def log_boundary(
    logger: logging.Logger,
    operation: str,
    **context: object,
) -> AsyncIterator[None]:
    """외부 서비스 호출 경계의 시작·성공·실패를 표준 형식으로 기록.

    번역된 예외(HTTPException 등)가 상위에서 삼켜져 서버 로그에 남지 않는
    문제를 방지 — 경계에서 원본 실패를 먼저 관측한 뒤 예외를 재전파한다.

    Args:
        logger: 기록에 사용할 (호출 모듈의) 로거.
        operation: 경계 식별 라벨(예: ``kakao_token_exchange``).
        **context: 안전한 부가 컨텍스트(예: ``url=...``). token/PII 금지.

    Yields:
        None: ``async with`` 본문에서 실제 I/O 를 수행한다.
    """
    ctx = " ".join(f"{key}={value}" for key, value in context.items())
    logger.debug("[BOUNDARY] %s 시작 %s", operation, ctx)
    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status_code, int) and 400 <= status_code < 500:
            # 설정/클라이언트 오류(예: 카카오 KOE320) — 재현 가능·스택 불필요.
            logger.warning(
                "[BOUNDARY] %s 실패(4xx) status=%s %s (%.0fms): %s", operation, status_code, ctx, elapsed_ms, exc
            )
        else:
            # 서버 5xx·네트워크·예상 밖 버그 — 스택 포함해 원인 추적.
            logger.error("[BOUNDARY] %s 실패 %s (%.0fms)", operation, ctx, elapsed_ms, exc_info=exc)
        raise
    else:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("[BOUNDARY] %s 성공 %s (%.0fms)", operation, ctx, elapsed_ms)


# Global loggers for the application.
# FastAPI 프로세스가 ai_worker.* 모듈도 import 하므로 (예: RAG 응답 생성기)
# 그 namespace 도 INFO 핸들러를 미리 등록한다 — 그렇지 않으면 ai_worker.*
# INFO 가 root logger 의 default WARNING 에 걸려 누락된다.
default_logger = setup_logger()
_ai_worker_logger = setup_logger("ai_worker")
