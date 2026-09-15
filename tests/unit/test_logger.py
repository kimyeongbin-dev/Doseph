"""Unit tests for app.core.logger — file handler + JSON formatter + rotation.

각 케이스는 독립된 ``LOG_DIR`` (tmp_path) 와 unique logger 이름을 사용해
이전 테스트의 logger 인스턴스가 쌓아둔 핸들러를 침범하지 않는다.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path
from uuid import uuid4

import pytest

from app.core import logger as logger_module


@pytest.fixture
def isolated_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """LOG_DIR 환경변수를 tmp_path 로 격리."""
    monkeypatch.setenv(logger_module._LOG_DIR_ENV, str(tmp_path))
    return tmp_path


def _unique_name() -> str:
    """매 테스트마다 새 logger namespace — 캐시 충돌 방지."""
    return f"test_logger_{uuid4().hex[:8]}"


@pytest.mark.usefixtures("isolated_log_dir")
class TestSetupLoggerHandlers:
    def test_attaches_console_and_file_handler(self) -> None:
        name = _unique_name()
        log = logger_module.setup_logger(name)

        handler_types = {type(h).__name__ for h in log.handlers}
        assert "StreamHandler" in handler_types
        # 로깅 정비(B0~B6)에서 시간(3h)+크기(10MB) **병행** 회전으로 교체됐다.
        assert "SizeTimedRotatingFileHandler" in handler_types

    def test_idempotent_no_duplicate_handlers(self) -> None:
        name = _unique_name()
        first = logger_module.setup_logger(name)
        before = len(first.handlers)

        second = logger_module.setup_logger(name)
        assert second is first
        assert len(second.handlers) == before


class TestJsonFormatter:
    def test_includes_required_fields(self) -> None:
        formatter = logger_module.JsonFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )

        line = formatter.format(record)
        payload = json.loads(line)

        assert payload["level"] == "INFO"
        assert payload["logger"] == "test.module"
        assert payload["msg"] == "hello world"
        assert payload["line"] == 42
        assert "ts" in payload
        assert payload["ts"].endswith("+00:00")  # UTC ISO 8601

    def test_serializes_exception_stack_trace(self) -> None:
        formatter = logger_module.JsonFormatter()

        def _trigger() -> None:
            raise ValueError("kaboom")

        try:
            _trigger()
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test.module",
                level=logging.ERROR,
                pathname="test.py",
                lineno=10,
                msg="failure",
                args=None,
                exc_info=sys.exc_info(),
            )

        payload = json.loads(formatter.format(record))
        assert "exception" in payload
        assert "ValueError: kaboom" in payload["exception"]


class TestFileWritesJsonLines:
    def test_info_log_appears_as_json_line(self, isolated_log_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # ⚠️ JSON 포맷은 **prod 전용**이다(로컬 기본은 사람이 읽는 형식).
        #    이 클래스의 의도가 "파일에 JSON 라인이 쌓인다" 이므로 prod 를 강제한다.
        #    이 줄이 없던 탓에 로컬 포맷을 json.loads 로 파싱하다 실패하고 있었다(QA-27).
        monkeypatch.setenv("ENV", "prod")
        name = _unique_name()
        log = logger_module.setup_logger(name)

        log.info("event %s", "ready")
        for handler in log.handlers:
            handler.flush()

        log_file = isolated_log_dir / f"{name}.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8").strip()
        assert content, "log file should not be empty"
        last_line = content.splitlines()[-1]
        payload = json.loads(last_line)
        assert payload["msg"] == "event ready"
        assert payload["level"] == "INFO"


class TestRotation:
    def test_rotation_creates_backup_when_max_bytes_exceeded(self, isolated_log_dir: Path) -> None:
        name = _unique_name()
        log = logger_module.setup_logger(name)

        # 한 RotatingFileHandler 만 강제로 작은 maxBytes 로 교체 — 실제 10MB 채우지 않고 회전 트리거.
        for handler in list(log.handlers):
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                log.removeHandler(handler)
                handler.close()
        small = logging.handlers.RotatingFileHandler(
            isolated_log_dir / f"{name}.log",
            maxBytes=512,  # 512 bytes
            backupCount=2,
            encoding="utf-8",
        )
        small.setFormatter(logger_module.JsonFormatter())
        log.addHandler(small)

        for i in range(50):
            log.info("payload-%d %s", i, "x" * 60)
        small.flush()

        backup = isolated_log_dir / f"{name}.log.1"
        assert backup.exists(), "RotatingFileHandler 가 backup 파일을 생성해야 한다"
