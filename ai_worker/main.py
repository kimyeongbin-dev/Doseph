"""AI Worker Entry Point - Final Merged Version.

This module contains the main entry point for the AI worker service.
Includes Redis connection retry logic and RQ version compatibility handling.
"""

from pathlib import Path
import signal
import sys
import time
from typing import Any

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rq import Queue, SimpleWorker

from ai_worker.core.config import config
from ai_worker.core.logger import get_logger
from ai_worker.core.redis_client import make_sync_redis

logger = get_logger(__name__)


# Graceful shutdown flag
shutdown_requested = False


def signal_handler(signum: int, _frame: object) -> None:
    """Signal handler for SIGTERM and SIGINT.

    Args:
        signum: Signal number.
        _frame: Current stack frame (unused).
    """
    global shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info("Received %s, initiating graceful shutdown...", sig_name)
    shutdown_requested = True


def check_redis_connection() -> bool:
    """Check Redis connection status.

    Returns:
        bool: True if Redis is connected, False otherwise.
    """
    try:
        redis_client = make_sync_redis(config.REDIS_URL, socket_timeout=5)
        redis_client.ping()
        return True
    # 🟠 QA-51: BLE001 은 부채다 — redis 예외로 좁힐 수 있다. 행동 변경이라 미뤘다.
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis connection failed: %s", e)
        return False


def _wait_for_redis(max_retries: int = 30, delay_sec: int = 2) -> None:
    """Block until Redis is reachable or exhaust the retry budget.

    Args:
        max_retries: Maximum number of probe attempts.
        delay_sec: Sleep between probes (seconds).

    Raises:
        SystemExit: If Redis stays unreachable past ``max_retries``.
    """
    for attempt in range(1, max_retries + 1):
        if check_redis_connection():
            logger.info("Redis connected successfully")
            return
        logger.info("Waiting for Redis... (%d/%d)", attempt, max_retries)
        time.sleep(delay_sec)
    logger.error("Failed to connect to Redis after max retries. Exiting.")
    sys.exit(1)


def _build_worker_queues(redis_conn: Any) -> list[Queue]:
    """Wire the AI + default RQ queues onto a shared Redis connection."""
    return [Queue("ai", connection=redis_conn), Queue("default", connection=redis_conn)]


def _run_supervision_loop(redis_conn: Any, queues: list[Queue]) -> None:
    """Run RQ ``SimpleWorker`` under a restart-on-stall supervision loop.

    SimpleWorker = no fork (PyTorch / fork deadlock 회피). worker_ttl=180s 으로
    BLPOP 자연 반환 주기를 짧게 유지해 Docker bridge / WSL2 NAT 의 idle TCP
    drop 을 회피. work() 가 예외 없이 return 하는 비정상 케이스 (RQ 내부의
    redis.TimeoutError swallow) 는 ``worker._stop_requested`` 로 진짜 종료와
    구분한다.
    """
    while True:
        worker = SimpleWorker(queues, connection=redis_conn, worker_ttl=180)
        try:
            worker.work(with_scheduler=True)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Termination signal received, exiting supervision loop")
            return
        except Exception:
            logger.exception("Worker crashed unexpectedly")
            sys.exit(1)

        if worker._stop_requested:  # noqa: SLF001 — RQ public API 부재, 종료 신호 구분 위해 직접 참조
            logger.info("Stop requested, exiting supervision loop")
            return

        logger.warning("Worker exited unexpectedly (likely Redis timeout); restarting in 2s")
        time.sleep(2)


def main() -> None:
    """Main worker entry — install signals, connect Redis, run supervision loop."""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("AI Worker starting...")
    logger.info("Timezone: %s", config.TIMEZONE)

    _wait_for_redis()

    # make_sync_redis 가 keepalive + retry 옵션을 일괄 적용 (BLPOP idle 후 재연결 안정화).
    redis_conn = make_sync_redis(config.REDIS_URL)
    queues = _build_worker_queues(redis_conn)
    logger.info("AI Worker ready - waiting for tasks...")
    _run_supervision_loop(redis_conn, queues)


if __name__ == "__main__":
    main()
