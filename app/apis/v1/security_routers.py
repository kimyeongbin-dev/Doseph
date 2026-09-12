"""보안 리포트 수신 라우터.

CSP 위반 리포트를 수신해 마스킹 로깅한다. 인증 없이 공개되지만 rate-limit
미들웨어(EXCLUDED 아님)가 IP 기반으로 남용을 억제한다.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.services.security_service import CspReportService

router = APIRouter(prefix="/security", tags=["Security"])


def get_csp_report_service() -> CspReportService:
    """Provide a CspReportService instance (DI hook for tests)."""
    return CspReportService()


CspReportServiceDep = Annotated[CspReportService, Depends(get_csp_report_service)]


# ── CSP 위반 리포트 수신 (POST /security/csp-report) ──────────────────
# 흐름: body JSON 파싱 -> 위반 정규화 -> 없으면 400 / 있으면 마스킹 로깅 -> 204
@router.post("/csp-report", status_code=status.HTTP_204_NO_CONTENT)
async def receive_csp_report(request: Request, service: CspReportServiceDep) -> Response:
    """Receive and log browser CSP violation reports.

    Accepts both legacy report-uri and Reporting API payloads. Returns 204 on a
    valid report, 400 when the body is not a recognizable CSP report.

    Args:
        request: Incoming request carrying the raw report body.
        service: CSP report parsing/logging service.

    Returns:
        Response: 204 on success, 400 on malformed input.
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    violations = service.parse_violations(payload)
    if not violations:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    service.log_violations(violations)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
