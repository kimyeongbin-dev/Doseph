"""Health check endpoints module.

This module provides health check endpoints for monitoring application status,
including liveness and readiness probes for container orchestration.

보안 정책 (의도된 NO-AUTH):
    Kubernetes/ECS liveness·readiness probe / nginx upstream health check 에서
    호출되므로 인증을 요구하지 않는다. 응답 본문엔 사용자 식별 정보·내부 자원
    상태가 포함되지 않으며, 외부에서 보더라도 service availability 외에는
    leak 되는 정보가 없다.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check() -> dict[str, str]:
  """Basic health check endpoint - liveness probe.

  의도된 NO-AUTH endpoint — 모듈 docstring "보안 정책" 참고.

  Returns:
      dict[str, str]: Health status response.
  """
  return {"status": "healthy"}


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
  """Readiness check endpoint - readiness probe.

  의도된 NO-AUTH endpoint — 모듈 docstring "보안 정책" 참고.

  TODO: Add checks for DB connection, Redis connection, etc.

  Returns:
      dict[str, str]: Readiness status response.
  """
  return {"status": "ready"}
